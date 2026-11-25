# Fallback transcript

> **This is a recorded run, not live output.** Use it only if the live demo is slow or unavailable, and say so:
> "Here's the same request from a validated run earlier."

This conversation went through the Contoso Air web app (`python scripts/validate_webapp.py --transcript …`). It used
the same Foundry agent as the playground and passed all 34 automated checks. The airline system's current date was
2026-11-24, so "tomorrow" is November 25. All names, codes and phone numbers are synthetic.

The agent writes each reply fresh, so live wording can differ from this transcript. The facts and the
recommendation should not.

Screenshots from a separate recorded run of the same scenario:
[clean start](assets/web-clean-start.png) · [in progress](assets/hero-in-progress.png) ·
[completed](assets/hero-completed.png).

---

## 1. Hero prompt (43.8 s)

**Customer:** My flight tomorrow was cancelled. I'm traveling with my wife and two children. Can you help me figure
out what to do?

*Progress shown: Checking your trip… → Checking flight status… → Checking Contoso Air policies… → Finding
alternative flights… → Reviewing your options… → Checking flight status…*

**Travel Assistant:**

> Alex, I'm sorry for the disruption—I found an option that keeps all four of you together.
>
> **What I confirmed:** Your Seattle–JFK flight CT218 tomorrow, November 25, is cancelled because of an operational
> disruption. All four passengers are booked in Economy Plus.
>
> **My recommendation: CT226 nonstop tomorrow, departing Seattle at 9:20 AM and arriving JFK at 5:45 PM**, both local
> times. It's currently on time, with six Economy Plus seats available. You'd leave 1 hour 10 minutes earlier and
> arrive 1 hour 5 minutes earlier than originally planned; travel time is 5 hours 25 minutes.
>
> **Other options:**
> - The 7:10 AM connection through Chicago arrives at 6:20 PM, but requires a downgrade to Main Cabin for everyone,
>   a 1-hour-50-minute layover, and 8 hours 10 minutes of travel.
> - The 3:45 PM nonstop cannot accommodate all four of you.
>
> **What's covered:** Our Flight Disruption and Rebooking Policy provides eligible rebooking without change fees or
> fare differences, or a refund of unused tickets if you decline all alternatives. Your Gold status gives your whole
> reservation priority, but doesn't guarantee seats.
>
> Would you like to proceed with CT226 for all four in Economy Plus? Nothing is held or changed yet.

## 2. Follow-up (6.7 s)

**Customer:** Why is that better than the connection?

**Travel Assistant:**

> Alex, **CT226 is better because it keeps all four of you in Economy Plus, avoids a connection, and arrives
> earlier.**
>
> Here's the comparison for tomorrow, November 25—all times are local:
>
> | | CT226 nonstop | Connection through Chicago |
> |---|---|---|
> | Leaves Seattle | 9:20 AM | 7:10 AM |
> | Arrives JFK | 5:45 PM | 6:20 PM |
> | Total travel | 5 hours 25 minutes | 8 hours 10 minutes |
> | Cabin for all four | Economy Plus | Main Cabin |
> | Connection | None | 1 hour 50 minutes |
>
> The nonstop lets you **leave 2 hours 10 minutes later yet arrive 35 minutes earlier**. The connection has only two
> Economy Plus seats available across both flights.
>
> Our Flight Disruption and Rebooking Policy favors keeping your party together in the booked cabin and a comparable
> nonstop itinerary. A downgrade requires your consent and a refund of the affected segment's fare difference.
>
> Would you like to proceed with CT226 for all four in Economy Plus? Nothing is held or changed yet.

## 3. Hotel question (7.7 s)

**Customer:** Do I qualify for a hotel?

*Progress shown: Checking Contoso Air policies…*

**Travel Assistant:**

> Alex, **based on your current trip and the available same-day alternative, you don't qualify for a complimentary
> hotel.**
>
> Under our **Meal and Hotel Assistance Policy**, a hotel requires a controllable disruption that forces an overnight
> stay **away from your home airport metropolitan area**. Your cancellation is controllable, but:
> - Seattle is listed as your home airport, and hotels aren't provided in the home airport area.
> - The recommended CT226 departs on your original travel date, November 25, so it doesn't require an overnight
>   delay.
>
> Your Gold status doesn't change hotel eligibility. If there are special circumstances you'd like reviewed, the
> IROPS Recovery Desk at **1-800-555-0161** can consider an exception, but approval isn't guaranteed.
>
> You can still rebook all four passengers on an eligible alternative without change fees or fare differences, or
> request a refund of the unused tickets if you decline all alternatives.

## 4. "Book it." (6.3 s)

**Customer:** Book it.

**Travel Assistant:**

> Alex, I can't complete the booking in this chat, so **nothing has been changed or held**.
>
> Please call your dedicated **Gold service line at 1-800-555-0157, available 24/7**, to request the change. Here's
> exactly what to request:
>
> - **Replace cancelled CT218 with CT226 nonstop** on **November 25, 2026**
> - **Seattle (SEA) 9:20 AM → New York (JFK) 5:45 PM**, local airport times
> - **All four passengers:** Alex, Jamie, Taylor and Jordan Johnson
> - **Economy Plus for everyone**
> - Reservation code: **CT8K2P**
>
> Under our Flight Disruption and Rebooking Policy, this eligible replacement has **no change fee or fare
> difference**. Six Economy Plus seats were available when I checked, but availability can change until the
> rebooking is completed.

---

**What to point out:** the customer never gave a confirmation code, flight number, loyalty tier, policy or list of
flights. CT226 was the **second** search result, not the first: the API returns options in departure order, and the
agent chose the one that keeps all four together in Economy Plus.
