"""Per-turn, owner-scoped evidence. Never collect HTTP Authorization headers."""
from contextvars import ContextVar
import copy
import time

active = ContextVar('llm_trace', default=None)

def record(event):
    trace = active.get()
    if trace is not None:
        trace['events'].append({'time': time.time(), **copy.deepcopy(event)})
