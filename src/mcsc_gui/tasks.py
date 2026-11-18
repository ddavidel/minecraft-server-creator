"""Handle background tasks."""

from __future__ import annotations

import threading
from time import sleep
from typing import Any, Callable
from uuid import uuid4

ALLOWED_ACTIONS = {
    "call",
    "process_output",
}


class Task:
    """A background activity with validation and minimal execution semantics."""

    def __init__(
        self,
        name: str = "",
        action: str = "",
        target: Any | Callable = None,
        actions: list[str] | None = None,
        repeat: bool = False,
        output_processor: Any | Callable = None,
        tick_interval: float = 10.0,
        args: tuple[Any, ...] | None = None,
        kwargs: dict[str, Any] | None = None,
    ) -> None:
        if not action and not actions:
            raise ValueError(
                "At least one parameter between 'action' and 'actions' has to be used"
            )

        declared_actions = list(actions or [])
        if action:
            declared_actions.append(action)

        invalid_actions = [item for item in declared_actions if item not in ALLOWED_ACTIONS]
        if invalid_actions:
            raise ValueError(f"Action '{invalid_actions[0]}' not recognized.")

        if ("process_output" in declared_actions) and output_processor is None:
            raise ValueError("No output processor provided.")
        if repeat and tick_interval < 0:
            raise ValueError("Invalid 'tick_interval' value.")
        if action == "call" and not callable(target):
            raise ValueError("'target' is not callable")
        if output_processor is not None and not callable(output_processor):
            raise ValueError("'output_processor' is not callable")

        self.name = name or str(uuid4())
        self.action = action
        self.actions = actions or []
        self.target = target
        self.repeat = repeat
        self.output_processor = output_processor
        self.tick_interval = tick_interval
        self.args = args or ()
        self.kwargs = kwargs or {}

    def tick(self) -> None:
        """Execute a single task cycle."""
        if self.action:
            self._process_action(self.action)
            return

        for action in self.actions:
            self._process_action(action)

    def _process_action(self, action: str) -> None:
        """Run an action for the task."""
        if action == "call":
            self._call(self.target, self.args, self.kwargs)
            return

        if action == "process_output":
            output = self._call(self.target, self.args, self.kwargs)
            self._call(self.output_processor, (output,))

    def _call(
        self,
        target: Callable,
        args: tuple[Any, ...] | None = None,
        kwargs: dict[str, Any] | None = None,
    ) -> Any:
        """Call a function or method with validated arguments."""
        if not callable(target):
            raise ValueError("'target' is not callable")
        call_args = args or ()
        call_kwargs = kwargs or {}
        return target(*call_args, **call_kwargs)


class TaskHandler:
    """Acts as a lightweight task scheduler for repeated and one-off background tasks."""

    tasks: list[Task] = []
    active = False
    _threads: dict[Task, threading.Thread] = {}

    @classmethod
    def start(cls) -> None:
        """Start all queued tasks."""
        cls.active = True
        for task in list(cls.tasks):
            cls._start_task_thread(task)

    @classmethod
    def stop(cls) -> None:
        """Stop background execution."""
        cls.active = False

    @classmethod
    def _start_task_thread(cls, task: Task) -> None:
        """Start a task in a dedicated thread."""
        cls._threads[task] = threading.Thread(target=cls._run, args=(task,), daemon=True)
        cls._threads[task].start()

    @classmethod
    def queue_task(cls, task: Task) -> None:
        """Add a task to the queue."""
        cls.tasks.append(task)
        if cls.active:
            cls._start_task_thread(task)

    @classmethod
    def _run(cls, task: Task) -> None:
        """Run the task, supporting repeated execution until stopped."""
        if not task.repeat:
            task.tick()
            if task in cls.tasks:
                cls.tasks.remove(task)
            return

        while cls.active:
            task.tick()
            sleep(task.tick_interval)
