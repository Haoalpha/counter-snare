"""Lớp dữ liệu "core banking" (chỉ đọc) + thuật toán khoanh vùng đường dây mule từ tài khoản hạt giống."""
from __future__ import annotations

from collections import deque
from dataclasses import dataclass

import pandas as pd

from .model import MuleModel, reason_codes, risk_band

MULE_THRESHOLD = 0.5


def mask_name(name: str) -> str:
    parts = str(name).split()
    return " ".join(p[0] + "*" * (len(p) - 1) if len(p) > 1 else p for p in parts)


def vnd(x: float) -> str:
    return f"{int(round(x)):,}".replace(",", ".") + " đ"


@dataclass
class Ring:
    seeds: list[str]
    nodes: dict
    edges: list[dict]
    summary: dict


class Bank:
    def __init__(self, accounts: pd.DataFrame, tx: pd.DataFrame, feats: pd.DataFrame, model: MuleModel, meta: dict):
        self.acc = accounts.set_index("account_id")
        self.tx = tx
        self.feats = feats
        self.model = model
        self.meta = meta
        self.p = model.predict(feats)
        self.by_src = tx.groupby("src").indices
        self.by_dst = tx.groupby("dst").indices
        dev = pd.concat([accounts[["account_id", "device_id"]], tx[["src", "device_id"]].rename(columns={"src": "account_id"})])
        dev = dev.drop_duplicates()
        self.dev_to_accts = dev.groupby("device_id")["account_id"].apply(set).to_dict()
        self.acct_to_devs = dev.groupby("account_id")["device_id"].apply(set).to_dict()

    # ---------- read tools ----------
    def exists(self, acct: str) -> bool:
        return acct in self.acc.index

    def profile(self, acct: str, masked: bool = False) -> dict:
        a = self.acc.loc[acct]
        f = self.feats.loc[acct]
        return {
            "account_id": acct, "bank": a["bank"],
            "holder_name": mask_name(a["holder_name"]) if masked else a["holder_name"],
            "age": int(a["age"]), "occupation": a["occupation"], "segment": a["segment"], "province": a["province"],
            "declared_income": int(a["declared_income"]), "open_date": str(pd.Timestamp(a["open_date"]).date()),
            "kyc_channel": a["kyc_channel"], "account_age_days": int(f["account_age_days"]),
        }

    def transactions(self, acct: str, limit: int = 50) -> pd.DataFrame:
        idx = list(self.by_src.get(acct, [])) + list(self.by_dst.get(acct, []))
        return self.tx.iloc[sorted(set(idx))].tail(limit)

    def risk(self, acct: str) -> dict:
        f = self.feats.loc[acct]
        p = float(self.p.get(acct, 0.0))
        red, green = reason_codes(f)
        return {"account_id": acct, "score": round(p, 4), "band": risk_band(p), "red_flags": red, "mitigating": green,
                "contributions": self.model.contributions(f) if p >= 0.2 else []}

    def infer_role(self, acct: str, sends_to_mule: bool) -> str:
        a = self.acc.loc[acct]
        if a["segment"] == "HE_THONG":
            return "sink"
        f = self.feats.loc[acct]
        p = float(self.p.get(acct, 0.0))
        ato = f["foreign_device_out_ratio"] > 0 and f["account_age_days"] > 180
        if p >= MULE_THRESHOLD and not ato:
            if f["cashout_ratio"] >= 0.3:
                return "cashout"
            ins = self.tx.iloc[list(self.by_dst.get(acct, []))]
            if len(ins):
                low = ins["src"].map(lambda s: self.p.get(s, 0.0) < MULE_THRESHOLD)
                if ins.loc[low.values, "amount"].sum() >= 0.5 * ins["amount"].sum():
                    return "collector"
            return "layer"
        if sends_to_mule:
            return "victim_ato" if ato else "victim"
        return "related"

    # ---------- ring expansion ----------
    def expand_ring(self, seeds: list[str], max_hops: int = 4, min_amount: int = 1_000_000, max_nodes: int = 160) -> Ring:
        seeds = [s for s in seeds if self.exists(s)]
        visited = {s: 0 for s in seeds}
        q = deque(seeds)
        edge_tx: dict[tuple, list[int]] = {}
        device_links: set[tuple] = set()
        while q and len(visited) < max_nodes:
            node = q.popleft()
            hop = visited[node]
            risky = node in seeds or self.p.get(node, 0) >= MULE_THRESHOLD
            if not risky or self.acc.loc[node, "segment"] == "HE_THONG":
                continue
            for col, idxs in (("dst", self.by_src.get(node, [])), ("src", self.by_dst.get(node, []))):
                sub = self.tx.iloc[list(idxs)]
                sub = sub[sub["amount"] >= min_amount]
                for nb, grp in sub.groupby(col):
                    key = (node, nb) if col == "dst" else (nb, node)
                    edge_tx.setdefault(key, []).extend(grp.index.tolist())
                    if nb not in visited and hop < max_hops:
                        visited[nb] = hop + 1
                        q.append(nb)
            # tài khoản dùng chung thiết bị với chủ sở hữu khác
            for d in self.acct_to_devs.get(node, set()):
                for other in self.dev_to_accts.get(d, set()):
                    if other == node or other not in self.acc.index:
                        continue
                    if self.acc.loc[other, "holder_id"] == self.acc.loc[node, "holder_id"]:
                        continue
                    if self.acc.loc[other, "segment"] == "HE_THONG":
                        continue
                    device_links.add(tuple(sorted((node, other))) + (d,))
                    if other not in visited and hop < max_hops and len(visited) < max_nodes:
                        visited[other] = hop + 1
                        q.append(other)

        mule_set = {n for n in visited if self.p.get(n, 0) >= MULE_THRESHOLD}
        nodes = {}
        for n in visited:
            sends_to_mule = any(src == n and dst in mule_set for (src, dst) in edge_tx)
            role = self.infer_role(n, sends_to_mule)
            if role == "related" and n not in seeds:
                continue
            a = self.acc.loc[n]
            nodes[n] = {
                "id": n, "role": role, "hop": visited[n], "seed": n in seeds, "bank": a["bank"],
                "holder_name": a["holder_name"], "holder_masked": mask_name(a["holder_name"]),
                "score": round(float(self.p.get(n, 0.0)), 4), "band": risk_band(float(self.p.get(n, 0.0))),
                "age": int(a["age"]), "account_age_days": int(self.feats.loc[n, "account_age_days"]),
            }
        edges = []
        for (s, d), idxs in edge_tx.items():
            if s not in nodes or d not in nodes:
                continue
            g = self.tx.loc[sorted(set(idxs))]
            edges.append({"src": s, "dst": d, "amount": int(g["amount"].sum()), "count": int(len(g)),
                          "first": str(g["ts"].min()), "last": str(g["ts"].max()), "tx_ids": g["tx_id"].tolist()[:8]})
        for a1, a2, d in device_links:
            if a1 in nodes and a2 in nodes:
                edges.append({"src": a1, "dst": a2, "device": d, "type": "device"})

        mule_roles = {"collector", "layer", "cashout"}
        victim_roles = {"victim", "victim_ato"}
        flow = [e for e in edges if e.get("type") != "device"]
        victim_loss = sum(e["amount"] for e in flow if nodes[e["src"]]["role"] in victim_roles and nodes[e["dst"]]["role"] in mule_roles)
        cashed = sum(e["amount"] for e in flow if nodes[e["src"]]["role"] in mule_roles and nodes[e["dst"]]["role"] == "sink")
        mule_in = sum(e["amount"] for e in flow if nodes[e["dst"]]["role"] in mule_roles and nodes[e["src"]]["role"] not in mule_roles)
        mule_out = sum(e["amount"] for e in flow if nodes[e["src"]]["role"] in mule_roles and nodes[e["dst"]]["role"] not in mule_roles)
        summary = {
            "n_mules": sum(1 for n in nodes.values() if n["role"] in mule_roles),
            "n_victims": sum(1 for n in nodes.values() if n["role"] in victim_roles),
            "n_victims_ato": sum(1 for n in nodes.values() if n["role"] == "victim_ato"),
            "roles": {r: sum(1 for n in nodes.values() if n["role"] == r) for r in ("collector", "layer", "cashout", "victim", "victim_ato", "sink")},
            "victim_loss": int(victim_loss), "cashed_out": int(cashed),
            "est_remaining": int(max(0, mule_in - mule_out)),
            "banks": sorted({n["bank"] for n in nodes.values() if n["role"] in mule_roles}),
            "devices": sorted({d for (_, _, d) in device_links}),
        }
        return Ring(seeds=seeds, nodes=nodes, edges=edges, summary=summary)

    # ---------- evidence ----------
    def evidence(self, ring: Ring) -> list[dict]:
        """Bằng chứng định lượng, sinh TẤT ĐỊNH từ dữ liệu. LLM chỉ được trích dẫn, không được bịa số."""
        ev = []

        def add(text: str, accts: list[str], tx_ids: list[str] | None = None, legal: str = ""):
            ev.append({"id": f"EV-{len(ev) + 1:02d}", "text": text, "accounts": accts, "tx_ids": tx_ids or [], "legal": legal})

        s = ring.summary
        add(f"Đường dây gồm {s['n_mules']} tài khoản nghi mule (gom: {s['roles']['collector']}, trung chuyển: {s['roles']['layer']}, "
            f"rút/chuyển ra: {s['roles']['cashout']}) tại các ngân hàng {', '.join(s['banks']) or '-'}.", [])
        add(f"{s['n_victims']} tài khoản nạn nhân đã chuyển tổng {vnd(s['victim_loss'])} vào đường dây; "
            f"{vnd(s['cashed_out'])} đã bị chuyển tới sàn tài sản số/rút tiền mặt; ước tính còn {vnd(s['est_remaining'])} "
            f"đang nằm trong các tài khoản thuộc đường dây.", [])
        if s["n_victims_ato"]:
            add(f"{s['n_victims_ato']} tài khoản nạn nhân có giao dịch ra từ thiết bị lạ (dấu hiệu bị chiếm quyền điều khiển điện thoại).",
                [n for n, v in ring.nodes.items() if v["role"] == "victim_ato"])
        if s["devices"]:
            add(f"{len(s['devices'])} thiết bị ({', '.join(s['devices'][:4])}) được dùng chung bởi nhiều chủ tài khoản trong đường dây.",
                [], legal="Luật PCRT 2022, Điều 28")
        mules = sorted([n for n in ring.nodes.values() if n["role"] in ("collector", "layer", "cashout")], key=lambda n: -n["score"])
        for n in mules[:8]:
            f = self.feats.loc[n["id"]]
            red, _ = reason_codes(f)
            ins = self.tx.iloc[list(self.by_dst.get(n["id"], []))]
            outs = self.tx.iloc[list(self.by_src.get(n["id"], []))]
            text = (f"TK {n['id']} ({n['bank']}, {n['role']}): mở {n['account_age_days']} ngày, nhận {len(ins)} giao dịch tổng "
                    f"{vnd(ins['amount'].sum())}, chuyển đi {len(outs)} giao dịch tổng {vnd(outs['amount'].sum())}. "
                    + " ".join(r["text"] + "." for r in red[:3]))
            add(text, [n["id"]], ins["tx_id"].tolist()[:3] + outs["tx_id"].tolist()[:3],
                legal="; ".join(sorted({r["legal"] for r in red[:3]})))
        return ev
