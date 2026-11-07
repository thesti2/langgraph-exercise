## Refund policy (implement in `check_policy`, no LLM)

`TODAY` is fixed in `orders.py` so results are deterministic.

1. **Final-sale** items are not refundable → recommendation `reject`.
2. Item reported **damaged / defective** → full refund to the original payment method,
   no matter how many days have passed.
3. ≤ **30 days** since delivery → full refund to the original payment method.
4. **31–60 days** → refund as **store credit** only.
5. **> 60 days** → recommendation `reject`.

**Auto-approve** only when *all* of these hold. Anything else goes to `human_review`.
- the recommendation is not `reject`
- refund amount ≤ **$100**
- the customer has **fewer than 3** refunds in the last 90 days