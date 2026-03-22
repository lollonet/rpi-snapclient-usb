# Fix Prompt — snapMULTY/client/common/docker/fb-display

## BUG-2 (Medium) — Broad `except Exception:` in `_get_lan_ip()`, line 51

### Current Code

```python
except Exception:
    return "?.?.?.?"
```

### Fix

```python
except OSError as e:
    logger.warning("Could not determine LAN IP: %s", e)
    return "?.?.?.?"
```

### Rationale

- `_get_lan_ip()` only does socket operations, so only `OSError` (and subclasses like
  `socket.error`) can legitimately occur.
- Catching `Exception` hides programming errors (e.g., `TypeError`, `AttributeError`)
  that should propagate during development.
- Adding a log message helps debug network issues on RPi deployments.
