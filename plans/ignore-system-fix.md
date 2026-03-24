# Ignore System Sleep Mode Fix

## Problem

The ignore system enters sleep mode correctly after 3 consecutive `<IGNORE>` responses, but immediately wakes up incorrectly, creating an infinite cycle.

## Root Cause

**Bug Location 1:** [`utils/sleep_mode_utils.py:184-185`](../utils/sleep_mode_utils.py:184)
```python
if hasattr(msg.raw_message, 'reference') and msg.raw_message.reference:
    is_reply_to_bot = True  # BUG: Treats ANY reply as reply to bot
```

**Bug Location 2:** [`messaging/pipeline.py:795-796`](../messaging/pipeline.py:795)
```python
if hasattr(msg.raw_message, 'reference') and msg.raw_message.reference:
    is_reply_to_bot = True  # BUG: Same issue
```

### Why This Fails

When users reply to each other's messages (not the bot), the code incorrectly sets `is_reply_to_bot = True`, causing false wake-ups.

### The Cycle

1. AI sends `<IGNORE>` 3 times → enters sleep mode ✓
2. User sends message that's a reply to another user
3. Wake-up detection incorrectly triggers ✗
4. AI wakes up, processes, sends `<IGNORE>` again
5. Repeat infinitely

## Solution

### 1. Fix `utils/sleep_mode_utils.py`

Make [`should_wake_from_sleep()`](../utils/sleep_mode_utils.py:102) async and add proper reply verification:

```python
async def should_wake_from_sleep(
    server_id: str,
    channel_id: str,
    ai_name: str,
    session: Dict[str, Any],
    pending_messages: List[Any],
    bot_user_id: Optional[int] = None
) -> Tuple[bool, bool]:
    # ... existing code ...
    
    # Check messages for wake-up patterns
    is_mentioned = False
    is_reply_to_bot = False
    message_content = ""
    
    if bot_user_id:
        for msg in pending_messages:
            message_content += msg.content + " "
            if hasattr(msg, 'raw_message') and msg.raw_message:
                # Check if bot is mentioned
                if hasattr(msg.raw_message, 'mentions'):
                    is_mentioned = is_mentioned or any(
                        m.id == bot_user_id for m in msg.raw_message.mentions
                    )
                
                # Check if message is a reply to bot (FIXED)
                if hasattr(msg.raw_message, 'reference') and msg.raw_message.reference:
                    try:
                        from utils.message_cache import fetch_message_cached
                        ref_msg_id = msg.raw_message.reference.message_id
                        ref_msg = await fetch_message_cached(
                            msg.raw_message.channel, 
                            str(ref_msg_id)
                        )
                        if ref_msg and ref_msg.author.id == bot_user_id:
                            is_reply_to_bot = True
                    except Exception as e:
                        # Conservative: if we can't verify, assume NOT a reply to bot
                        log.debug(f"Could not verify reply target: {e}")
                        pass
```

### 2. Fix `messaging/pipeline.py`

Update [`_check_if_should_wake()`](../messaging/pipeline.py:718) at line 795-796:

```python
# Check if message is a reply to bot (FIXED)
if hasattr(msg.raw_message, 'reference') and msg.raw_message.reference:
    try:
        from utils.message_cache import fetch_message_cached
        ref_msg_id = msg.raw_message.reference.message_id
        ref_msg = await fetch_message_cached(
            msg.raw_message.channel,
            str(ref_msg_id)
        )
        if ref_msg and ref_msg.author.id == bot_user_id:
            is_reply_to_bot = True
    except Exception as e:
        # Conservative: if we can't verify, assume NOT a reply to bot
        log.debug(f"Could not verify reply target: {e}")
        pass
```

### 3. Update Call Sites

**[`messaging/timing.py:159`](../messaging/timing.py:159)**
```python
in_sleep, should_wake = await should_wake_from_sleep(  # Add await
    server_id,
    channel_id,
    ai_name,
    session,
    pending,
    bot_user_id
)
```

**[`messaging/pipeline.py:301`](../messaging/pipeline.py:301)**
```python
in_sleep, should_wake = await should_wake_from_sleep(  # Add await
    server_id,
    channel_id,
    ai_name,
    session_with_context,
    pending,
    bot_user_id
)
```

## Key Design Decision: Conservative Error Handling

The existing code at [`messaging/pipeline.py:371-372`](../messaging/pipeline.py:371) uses aggressive wake-up:
```python
# (better to wake up unnecessarily than miss a wake-up)
is_reply_to_bot = True
```

**This is wrong for sleep mode.** The fix uses **conservative** error handling:
- If we can't verify the reply target → assume NOT a reply to bot
- Prevents false wake-ups and API spam
- Users can still wake the bot by mentioning it explicitly

## Testing

After implementing the fix, test:
1. AI enters sleep mode after 3 `<IGNORE>` responses
2. Users reply to each other's messages → AI stays asleep ✓
3. User mentions bot → AI wakes up ✓
4. User replies to bot's message → AI wakes up ✓

## Files to Modify

1. [`utils/sleep_mode_utils.py`](../utils/sleep_mode_utils.py:102) - Make async, fix reply detection
2. [`messaging/pipeline.py`](../messaging/pipeline.py:795) - Fix reply detection in `_check_if_should_wake()`
3. [`messaging/timing.py`](../messaging/timing.py:159) - Add `await` to call
4. [`messaging/pipeline.py`](../messaging/pipeline.py:301) - Add `await` to call
