"""End-to-end live flow: image -> condition -> valuation -> quote."""
from vision.gemini_vision import predict_condition
from valuation.appraiser import appraise_item
from strategy.agent import generate_quotes


def instant_offer(item_id, image_bytes, current_inventory, capital):
    cv = predict_condition(image_bytes)
    val = appraise_item(item_id, cv["condition_score"])
    bid, ask, action = generate_quotes(val["fair_market_value"], val["expected_days_to_sell"],
                                       current_inventory, capital)
    return {"offer_to_customer": float(bid), "list_price": float(ask), "action": str(action),
            "condition": cv, "valuation": val}
