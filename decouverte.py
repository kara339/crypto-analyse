import os
import sys
import time
import random
import requests
import pandas as pd

BASE = "https://api.coingecko.com/api/v3"
MAX_NOUVELLES = 10
MAX_TOTAL = 200
CAP_MIN = 1000000
VOLUME_MIN = 100000
PAUSE = 10
REGISTRE = "data/registre_pieces.csv"


def get_json(url, params=None, essais=4):
    for i in range(essais):
        r = requests.get(url, params=params, timeout=30)
        if r.status_code == 429:
            attente = 60 * (i + 1)
            print("pause", attente, "s")
            time.sleep(attente)
            continue
        r.raise_for_status()
        return r.json()
    raise RuntimeError("429 : trop de requetes")


def lire_pieces():
    f = open("pieces.txt")
    lignes = [l.strip() for l in f if l.strip()]
    f.close()
    return lignes


def marches(page):
    p = {}
    p["vs_currency"] = "usd"
    p["order"] = "market_cap_desc"
    p["per_page"] = 250
    p["page"] = page
    return get_json(BASE + "/coins/markets", p)


def ids_stables():
    p = {}
    p["vs_currency"] = "usd"
    p["category"] = "stablecoins"
    p["per_page"] = 250
    p["page"] = 1
    d = get_json(BASE + "/coins/markets", p)
    return set([x["id"] for x in d])


def tendance():
    d = get_json(BASE + "/search/trending")
    return [x["item"]["id"] for x in d.get("coins", [])]


def infos(ids):
    p = {}
    p["vs_currency"] = "usd"
    p["ids"] = ",".join(ids)
    p["per_page"] = 250
    return get_json(BASE + "/coins/markets", p)


def acceptable(x, stables):
    if x["id"] in stables:
        return False
    cap = x.get("market_cap") or 0
    vol = x.get("total_volume") or 0
    return cap >= CAP_MIN and vol >= VOLUME_MIN


def tirer(liste, n, exclus, stables):
    bons = [x for x in liste if x["id"] not in exclus and acceptable(x, stables)]
    random.shuffle(bons)
    return bons[:n]


def ajouter_pieces(ids):
    f = open("pieces.txt")
    texte = f.read()
    f.close()
    f = open("pieces.txt", "a")
    if texte and not texte.endswith("\n"):
        f.write("\n")
    for i in ids:
        f.write(i + "\n")
    f.close()


def ajouter_registre(lignes):
    os.makedirs("data", exist_ok=True)
    nouveau = pd.DataFrame(lignes)
    if os.path.exists(REGISTRE):
        nouveau = pd.concat([pd.read_csv(REGISTRE), nouveau], ignore_index=True)
    nouveau.to_csv(REGISTRE, index=False)


def main():
    ecrire = "ecrire" in sys.argv
    suivies = lire_pieces()
    exclus = set(suivies)
    place = min(MAX_NOUVELLES, MAX_TOTAL - len(suivies))
    if place <= 0:
        print("Liste pleine :", len(suivies), "pièces suivies")
        return
    stables = ids_stables()
    time.sleep(PAUSE)
    haut = marches(1)
    time.sleep(PAUSE)
    milieu = marches(2) + marches(3)
    time.sleep(PAUSE)
    ids_t = tendance()
    time.sleep(PAUSE)
    chaud = []
    if ids_t:
        chaud = infos(ids_t)
    choix = []
    sources = [(haut, 3, "grosse_capitalisation"), (milieu, 4, "capitalisation_moyenne"), (chaud, 3, "tendance")]
    for liste, n, nom_source in sources:
        for x in tirer(liste, n, exclus, stables):
            choix.append((x, nom_source))
            exclus.add(x["id"])
    choix = choix[:place]
    date = pd.Timestamp.now().strftime("%Y-%m-%d")
    lignes = []
    for x, nom_source in choix:
        l = {}
        l["date_ajout"] = date
        l["coin_id"] = x["id"]
        l["nom"] = x.get("name")
        l["source"] = nom_source
        l["rang_a_l_ajout"] = x.get("market_cap_rank")
        l["capitalisation_a_l_ajout"] = x.get("market_cap")
        l["volume_a_l_ajout"] = x.get("total_volume")
        lignes.append(l)
        print("candidate :", x["id"], "|", nom_source, "| rang", x.get("market_cap_rank"))
    if not lignes:
        print("Aucune nouvelle pièce trouvée.")
        return
    if ecrire:
        ajouter_pieces([l["coin_id"] for l in lignes])
        ajouter_registre(lignes)
        print(len(lignes), "pièces ajoutées.")
    else:
        print("Essai à blanc : rien n'est écrit. Ajoute le mot ecrire pour enregistrer.")


if __name__ == "__main__":
    main()
