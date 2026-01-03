# Manual QA Checklist - Calendar Timezone Feature

## Pre-requisites
- [ ] Backend server running (`python -m app.main`)
- [ ] User logged in with Google OAuth
- [ ] User has events in Google Calendar

---

## Scenario 1: Pacific Time User - "Tomorrow's Schedule"

**Setup**:
- Verify user's timezone in DB: `SELECT timezone FROM users WHERE email = 'your@email.com';`
- Should be `America/Los_Angeles` or similar Pacific timezone

**Steps**:
1. In chat, ask: **"What's my schedule tomorrow?"**
2. Observe the `get_current_datetime` tool output in logs/response

**Expected**:
- [ ] `get_current_datetime` shows the correct current date in Pacific time
- [ ] Timezone name `(America/Los_Angeles)` is included in output
- [ ] LLM correctly calculates tomorrow's date
- [ ] Events for tomorrow are returned

---

## Scenario 2: "What time is it?"

**Steps**:
1. Ask: **"What time is it?"**

**Expected**:
- [ ] Response shows current time
- [ ] Timezone is mentioned (e.g., "America/Los_Angeles")
- [ ] Time matches your local clock

---

## Scenario 3: Create Event - Verify Timezone

**Steps**:
1. Ask: **"Create a meeting tomorrow at 2pm called Test Meeting"**
2. Go to Google Calendar to verify the event

**Expected**:
- [ ] Event is created successfully
- [ ] In Google Calendar, event shows 2:00 PM in user's timezone
- [ ] Event is on the correct day (tomorrow)

---

## Scenario 4: Query Date Range

**Steps**:
1. Ask: **"What's my schedule from January 6th to January 10th?"**

**Expected**:
- [ ] All events in the specified date range are returned
- [ ] Events outside the range are NOT returned
- [ ] Times are displayed correctly

---

## Scenario 5: User with Many Events

**Setup**: User should have 15+ events on a single day

**Steps**:
1. Ask: **"What's my schedule for [date with many events]?"**

**Expected**:
- [ ] All events are returned (up to 50)
- [ ] NOT truncated at 10 (old limit)

---

## Scenario 6: Invalid Date Format Error

**Steps**:
1. Manually test the list_calendar_events tool with invalid params
   (Developer testing - use a tool call directly)

**Expected**:
- [ ] Clear error message about invalid format
- [ ] Suggests ISO format example like '2026-01-05T00:00:00'

---

## Scenario 7: Event Update Uses Correct Timezone

**Steps**:
1. Create an event
2. Update its time: **"Move my Test Meeting to 4pm"**
3. Check Google Calendar

**Expected**:
- [ ] Event time updated correctly in user's timezone

---

## Results Summary

| Scenario | Pass/Fail | Notes |
|----------|-----------|-------|
| 1 - Tomorrow's Schedule | | |
| 2 - What time is it? | | |
| 3 - Create Event | | |
| 4 - Query Date Range | | |
| 5 - Many Events | | |
| 6 - Invalid Date Error | | |
| 7 - Event Update | | |

**Tester**: _______________
**Date**: _______________
**Build/Commit**: _______________

