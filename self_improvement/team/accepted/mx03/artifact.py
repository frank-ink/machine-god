# artifact.py
class BudgetExceeded(Exception):
    pass


def greedy_relevance(items: list[dict], budget: int) -> list[str]:
    sorted_items = sorted(items, key=lambda x: (-x["relevance"], x["item_id"]))
    selected = []
    used_tokens = 0
    for item in sorted_items:
        item_tokens = item["tokens"]
        if used_tokens + item_tokens > budget:
            continue
        selected.append(item["item_id"])
        used_tokens += item_tokens
    return selected


def evaluate(compiles: list[dict], selector, budget: int) -> dict:
    n_eval = 0
    recall_sum = 0.0
    precision_sum = 0.0
    precision_count = 0
    er_at_budget_hits = 0
    total_tokens_used = 0
    for compile_data in compiles:
        compile_id = compile_data["id"]
        items = compile_data["items"]
        gold = compile_data["gold"]
        item_tokens = {item["item_id"]: item["tokens"] for item in items}
        selected_ids = selector(items, budget)
        for item_id in selected_ids:
            if item_id not in item_tokens:
                raise ValueError(f"Unknown item_id: {item_id}")
        tokens_used = sum(item_tokens.get(item_id, 0) for item_id in selected_ids)
        total_tokens_used += tokens_used
        if tokens_used > budget:
            raise BudgetExceeded(f"Budget exceeded for compile {compile_id}")
        selected_set = set(selected_ids)
        gold_set = set(gold)
        if len(gold) > 0:
            n_eval += 1
            intersection = selected_set & gold_set
            recall = len(intersection) / len(gold) if len(gold) > 0 else 0.0
            recall_sum += recall
            if len(intersection) > 0:
                er_at_budget_hits += 1
            if len(selected_set) > 0 and len(gold_set) > 0:
                precision = len(intersection) / len(selected_set)
                precision_sum += precision
                precision_count += 1
    recall = recall_sum / n_eval if n_eval > 0 else 0.0
    precision = precision_sum / precision_count if precision_count > 0 else 0.0
    er_at_budget = er_at_budget_hits / n_eval if n_eval > 0 else 0.0
    mean_tokens_used = total_tokens_used / len(compiles) if len(compiles) > 0 else 0.0
    return {
        "n_eval": n_eval,
        "recall": recall,
        "precision": precision,
        "er_at_budget": er_at_budget,
        "mean_tokens_used": mean_tokens_used
    }