"""Incoming support tickets (GIVEN). Each one should run on its own thread_id."""

TICKETS: dict[str, dict] = {
    "T1": {
        "from": "maya@example.com",
        "message": "Hi, the mug from order SF-1001 isn't the colour I expected. Can I get my money back?",
    },
    "T2": {
        "from": "dan@example.com",
        "message": "I'd like to return the ultrabook (order SF-1002). It's too heavy for travel. Refund please.",
    },
    "T3": {
        "from": "dan@example.com",
        "message": "I want to return the laptop I bought recently, it's not what I need. How do I get a refund?",
    },
    "T4": {
        "from": "priya@example.com",
        "message": "Order SF-1003 - the rain jacket doesn't fit. I know it's been a while, but can I return it?",
    },
    "T5": {
        "from": "leo@example.com",
        "message": "Changed my mind on the sneakers in SF-1004, please refund.",
    },
    "T6": {
        "from": "sam@example.com",
        "message": "Headphones from SF-1005 sound bad. Refund.",
    },
    "T7": {
        "from": "ana@example.com",
        "message": "My blender (order SF-1006) started smoking and the motor died. It's defective. I want a refund.",
    },
}
