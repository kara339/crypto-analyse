import os
import sys
import time
import requests
import numpy as np
import pandas as pd

# Ajoute ici les pièces à suivre (identifiants CoinGecko)
def lire_pieces():
    with open("pieces.txt") as f:
        return [l.strip() for l in f if l.strip()]


PIECES = lire_pieces()
FICHIER = "data/rapports_quotidiens.csv"

CHAINES = {"ethereum": "1", "binance-smart-chain": "56", "polygon-pos": "137",
           "arbitrum-one": "42161", "base": "8453", "optimistic-ethereum": "10",
           "avalanche": "43114", "robinhood": "4663"}
BRULES = {"0x000000000000000000000000000000000000dead",
          "0x0000000000000000000000000000000000000000"}

_cache = {}


def get_json(url, params=None, essais=4):
    cle = (url, tuple(sorted((params or {}).items())))
    if cle in _cache:
        return _cache[cle]
    for i in range(essais):
        r = requests.get(url, params=params, timeout=30)
        if r.status_code == 429:
            attente = 60 * (i + 1)
            print(f"  limite de requêtes atteinte, pause de {attente} s")
            time.sleep(attente)
            continue
        r.raise_for_status()
        j = r.json()
        _cache[cle] = j
        return j
    raise RuntimeError("429 : trop de requêtes")


def historique(coin_id, jours=365):
    d = get_json(f"https://api.coingecko.com/api/v3/coins/{coin_id}/market_chart",
                 {"vs_currency": "usd", "days": jours, "interval": "daily"})
    df = pd.DataFrame(d["prices"], columns=["date", "prix"])
    df["volume"] = [v[1] for v in d["total_volumes"]]
    df["date"] = pd.to_datetime(df["date"], unit="ms")
    return df


def caracteristiques(d):
    d = d.copy()
    d["date"] = pd.to_datetime(d["date"]).dt.normalize()
    d = d.drop_duplicates("date", keep="last").sort_values("date")
    if len(d) < 31:
        return None, d
    p = d["prix"].values[-31:]
    v = np.nan_to_num(d["volume"].values[-31:])
    rend = np.diff(p) / p[:-1]
    c = {}
    c["volatilite_30j"] = rend.std()
    c["pire_chute_30j"] = 1 - (p / np.maximum.accumulate(p)).min()
    c["var_7j"] = p[-1] / p[-8] - 1
    c["var_30j"] = p[-1] / p[0] - 1
    c["prix_vs_pic_30j"] = p[-1] / p.max()
    c["pic_vs_creux_30j"] = p.max() / p.min()
    c["volume_moyen_30j"] = np.log10(v.mean() + 1)
    c["tendance_volume"] = v[-7:].mean() / (v.mean() + 1e-9)
    return c, d


def est_brule(h):
    a = h["address"].lower()
    return h.get("tag") == "Dead" or a in BRULES or a.startswith("0xdead")


def collecter(coin_id):
    d = get_json(f"https://api.coingecko.com/api/v3/coins/{coin_id}",
                 {"localization": "false", "tickers": "false",
                  "community_data": "false", "developer_data": "false"})
    m = d.get("market_data", {})
    ligne = {"date": pd.Timestamp.now().strftime("%Y-%m-%d"),
             "coin_id": coin_id, "nom": d.get("name"),
             "rang": d.get("market_cap_rank"),
             "capitalisation": (m.get("market_cap") or {}).get("usd"),
             "volume_24h": (m.get("total_volume") or {}).get("usd"),
             "categories": "|".join(c for c in (d.get("categories") or []) if c),
             "natif": not d.get("asset_platform_id")}
    ligne["prix"] = (m.get("current_price") or {}).get("usd")
    try:
        c, _ = caracteristiques(historique(coin_id))
        if c:
            ligne.update(c)
    except Exception as e:
        ligne["erreur_marche"] = str(e)[:80]

    for plateforme, adresse in (d.get("platforms") or {}).items():
        if adresse and plateforme in CHAINES:
            try:
                r = get_json(f"https://api.gopluslabs.io/api/v1/token_security/{CHAINES[plateforme]}",
                             {"contract_addresses": adresse})
                s = (r.get("result") or {}).get(adresse.lower(), {})
                holders = s.get("holders", [])
                pct = sorted((float(h["percent"]) for h in holders if not est_brule(h)), reverse=True)
                ligne.update({
                    "chaine": plateforme,
                    "nb_detenteurs": s.get("holder_count"),
                    "top1_pct": round(pct[0] * 100, 2) if pct else None,
                    "top10_pct": round(sum(pct) * 100, 2) if pct else None,
                    "brule_pct": round(sum(float(h["percent"]) for h in holders if est_brule(h)) * 100, 2),
                    "proprietaire_renonce": s.get("owner_address") in (None, "", "0x0000000000000000000000000000000000000000"),
                    "honeypot": s.get("is_honeypot"),
                    "mintable": s.get("is_mintable"),
                    "proxy": s.get("is_proxy"),
                    "suspendable": s.get("transfer_pausable"),
                    "liste_noire": s.get("is_blacklisted"),
                    "taxe_achat": s.get("buy_tax"),
                    "taxe_vente": s.get("sell_tax"),
                })
            except Exception as e:
                ligne["erreur_securite"] = str(e)[:80]
            break
    return ligne


def main():
    os.makedirs("data", exist_ok=True)
    lignes = []
    for coin in PIECES:
        try:
            lignes.append(collecter(coin))
            print("collecté :", coin)
        except Exception as e:
            print("échec :", coin, "->", str(e)[:100])
        time.sleep(30)

    if not lignes:
        sys.exit("Aucune pièce collectée : exécution marquée en échec.")

    nouveau = pd.DataFrame(lignes)
    if os.path.exists(FICHIER):
        nouveau = pd.concat([pd.read_csv(FICHIER), nouveau], ignore_index=True)
    nouveau = nouveau.drop_duplicates(["date", "coin_id"], keep="last")
    nouveau.to_csv(FICHIER, index=False)
    print("Fichier mis à jour :", len(nouveau), "lignes au total")


if __name__ == "__main__":
    main()
