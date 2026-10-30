import asyncio
from sidekick import SideKick

async def main():

    sidekick = SideKick()
    await sidekick.setup()

    AGENT_TASK = """Find me the best round-trip flight from New York to London, leaving around
    November 10, 2026 and returning a week later. I care about price first, then total journey time,
    and I'd rather avoid itineraries with two or more stops. Only report fares you actually found.
    Write your top three options to flights.md (airline, times, stops, price), with a clear
    recommendation, then send me a push notification with the price of your top pick."""

    AFENT_CRITERIA = """
    flights.md has three specific options with airline, times, stops (none with two or more) and price, 
    plus a clear recommendation, and a push notification was sent whose price matches the recommended option.
    """

    history = await sidekick.run_turn(
        AGENT_TASK,
        AFENT_CRITERIA,
        history = []
    )

    print(history[-1]["content"])

    for todo in sidekick.todos:
        print(f"[{todo['status']}] {todo['content']}")

    while sidekick.paused:

        print("\n" + history[-1]["content"])
        user_input = input("\nDo you approve this approve? (Y / N): ")

        if user_input.strip().lower() in ("y", "yes", "ok"):
            print("[STATUS] Approved! Continuing execution...")
            history = await sidekick.resume(history)

        else:
            print("[STATUS] Rejected! Execution undone.")
            sidekick.paused = False
            break

    for entry in history[-2:]:
        print(f"[{entry['role']}] {entry['content']}\n")

if __name__ == "__main__":
    asyncio.run(main())
