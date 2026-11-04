"""Select independent providers without translating Protocol 1 fields."""
import asyncio

from .offline_replay import OfflineReplay


class TelemetrySources:
    def __init__(self, live, mode="LIVE_LAPTOP1"):
        if mode not in {"LIVE_LAPTOP1", "OFFLINE_REPLAY"}:
            raise ValueError("SKYNEX_DATA_SOURCE must be LIVE_LAPTOP1 or OFFLINE_REPLAY.")
        self.live = live
        self.replay = OfflineReplay()
        self.mode = mode
        self.switch_lock = asyncio.Lock()

    def start(self):
        if self.mode == "LIVE_LAPTOP1":
            self.live.start()

    async def select(self, mode):
        async with self.switch_lock:
            if mode == self.mode:
                return self.snapshot()
            if mode == "OFFLINE_REPLAY":
                self.mode = mode
                await self.live.stop()
            elif mode == "LIVE_LAPTOP1":
                self.replay.pause_if_running()
                self.mode = mode
                self.live.start()
            else:
                raise ValueError("Unknown telemetry source.")
            return self.snapshot()

    def snapshot(self):
        if self.mode == "OFFLINE_REPLAY":
            return self.replay.snapshot()
        return {"mode": self.mode, **self.live.snapshot()}
