"""The games the app knows about and where each one keeps its files.

Marvel Champions keeps the original layout at the app root (catalog.json, library/, backs/). The other games live under
games/<id>/ with the same three pieces. "kind" says which selection model the UI and the order builder use:
  mc    - heroes / campaign boxes / scenario packs (mc_order.py)
  sets  - cycles -> packs -> sections of cards, images imported from Proxy Nexus exports (set_order.py)
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ORDERS = os.path.join(HERE, "orders")

GAMES = {
    "mc": {"name": "Marvel Champions", "kind": "mc", "dir": HERE, "order_name": "marvel-order",
           "back_kinds": ("player", "encounter", "villain"), "default_back": "original"},
    "arkham": {"name": "Arkham Horror LCG", "kind": "sets", "dir": os.path.join(HERE, "games", "arkham"),
               "order_name": "arkham-order", "back_kinds": ("player", "encounter"), "default_back": "original"},
    "lotr": {"name": "The Lord of the Rings LCG", "kind": "sets", "dir": os.path.join(HERE, "games", "lotr"),
             "order_name": "lotr-order", "back_kinds": ("player", "encounter", "quest"), "default_back": "alep"},
}
DEFAULT = "mc"


def get(game):
    if game not in GAMES:
        raise KeyError(f"unknown game '{game}'")
    return GAMES[game]


def paths(game):
    g = get(game)
    return {"dir": g["dir"], "catalog": os.path.join(g["dir"], "catalog.json"), "library": os.path.join(g["dir"], "library"),
            "backs": os.path.join(g["dir"], "backs")}


def listing():
    return [{"id": k, "name": v["name"], "kind": v["kind"], "order_name": v["order_name"], "default_back": v["default_back"]}
            for k, v in GAMES.items()]
