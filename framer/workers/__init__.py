"""Threads + main-loop bridge — the only layer where the two meet.

All GTK calls happen on the main thread only; worker threads push plain
events onto queues that the Dispatcher drains with a 60 ms GLib tick.
"""
