import sys
import datetime
import asyncio

from aiohttp_json_rpc import JsonRpcClient


class WorkerClient(JsonRpcClient):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.add_methods(
            ("", self.start_job),
        )
        self.current_job = None
        self._id = None

    def set_id(self, worker_id):
        self._id = worker_id

    async def start_job(self, job_data):
        if self.current_job is not None:
            return False

        print("Got new job {}".format(str(job_data)))
        self.current_job = job_data
        return True

    def finish_job(self, success, message, data):
        self._loop.create_task(self._finish_job(success, message, data))

    async def _finish_job(self, success, message, data):
        job_id = self.current_job["job_id"]
        self.current_job = None

        return await self.call(
            "job_done", [self._id, job_id, success, message, data]
        )


class WorkerJobsConnection:
    retry_time_seconds = 5

    def __init__(self, server_url, host_name, loop=None):
        self.client = None
        self._loop = loop

        self._host_name = host_name
        self._server_url = server_url

        self._is_running = False
        self._connecting = False
        self._connected = False
        self._stopped = False

    def stop(self):
        print("Stopping worker")
        self._stopped = True

    @property
    def is_running(self):
        return self._is_running

    @property
    def current_job(self):
        if self.client is not None:
            return self.client.current_job
        return None

    def finish_job(self, success=True, message=None, data=None):
        if self.client is None:
            print((
                "Couldn't sent job status to server because"
                " client is not connected."
            ))
        else:
            self.client.finish_job(success, message, data)

    async def main_loop(self):
        self._is_running = True

        while not self._stopped:
            start_time = datetime.datetime.now()
            await self._connection_loop()
            delta = datetime.datetime.now() - start_time
            print("Client was connected {}".format(str(delta)))
            # Check if was stopped and stop while loop in that case
            if self._stopped:
                break

            if delta.seconds < 60:
                print((
                    "Can't connect to server will try in {} seconds."
                ).format(self.retry_time_seconds))

                await asyncio.sleep(self.retry_time_seconds)
        self._is_running = False

    async def _connect(self):
        self.client = WorkerClient()
        print("Connecting to {}".format(self._server_url))
        await self.client.connect_url(self._server_url)

    async def _connection_loop(self):
        self._connecting = True
        asyncio.run_coroutine_threadsafe(
            self._connect(), loop=self._loop
        )

        while self._connecting:
            if self.client is None:
                await asyncio.sleep(0.07)
                continue
            session = getattr(self.client, "_session", None)
            ws = getattr(self.client, "_ws", None)
            if session is not None:
                if session.closed:
                    self._connecting = False
                    self._connected = False
                    break

                elif ws is not None:
                    self._connecting = False
                    self._connected = True

            if self._stopped:
                break

            await asyncio.sleep(0.07)

        if not self._connected:
            self.client = None
            return

        worker_id = await self.client.call(
            "register_worker", [self._host_name]
        )
        self.client.set_id(worker_id)
        print(
            "Registered as worker with id {}".format(worker_id)
        )
        counter = 0
        while self._connected and self._loop.is_running():
            if self._stopped or ws.closed:
                break

            if self.client.current_job:
                if counter == 3:
                    counter = 0
                    self.finish_job()
                else:
                    counter += 1

            await asyncio.sleep(0.3)

        await self._stop_cleanup()

    async def _stop_cleanup(self):
        print("Cleanup after stop")
        if self.client is not None and hasattr(self.client, "_ws"):
            await self.client.disconnect()

        self.client = None
        self._connecting = False
        self._connected = False
