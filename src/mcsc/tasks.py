"""Handle background tasks"""

from time import sleep
from uuid import uuid4
from typing import Any, Callable
import threading


ALLOWED_ACTIONS = [
    "call",  # calls target
    "process_output",  # processed the output of target
]


class Task:
    """An activity to be handled

    Available actions:
        call: calls 'target' function
        process_output: calls target function and processes output by passing it
        to 'output_processor'

    Args:
        name (str, optional): name of the task. If not passed a uuid4 is generated.
        action (str, optional): single action of the task.
        actions(list[str], optional): multiple actions of the task.
        target (Any, optional): target object
    """

    def __init__(
        self,
        name: str = "",
        action: str = "",
        target: Any | Callable = None,
        actions: list = None,
        repeat: bool = False,
        output_processor: Any | Callable = None,
        tick_interval: float = 10.0,
        args: tuple = None,
        kwargs: dict = None,
    ):
        # Validate
        if not action and not actions:
            raise ValueError(
                "At least one parameter between 'action' and 'actions' has to be used"
            )
        if action and action not in ALLOWED_ACTIONS:
            raise ValueError(f"Action '{action}' not recognized.")

        actions_test = [a not in ALLOWED_ACTIONS for a in actions]
        if actions and any(actions_test):
            raise ValueError(
                f"Action '{actions[actions_test.index(True)]}' not recognized."
            )

        if (
            action == "process_output" or "process_output" in actions
        ) and output_processor is None:
            raise ValueError("No output processor provided.")
        if repeat and tick_interval < 0:
            raise ValueError("Invalid 'tick_interval' value.")
        if action == "call" and not callable(target):
            raise ValueError("'target' is not callable")
        if output_processor is not None and not callable(output_processor):
            raise ValueError("'output_processor' is not callable")

        self.name = name or uuid4()
        self.action = action
        self.actions = actions
        self.target = target
        self.repeat = repeat
        self.output_processor = output_processor
        self.tick_interval = tick_interval
        self.args = args
        self.kwargs = kwargs

    def tick(self):
        """Tick for repeated Tasks"""
        if self.action:
            self._process_action(self.action)
        elif self.actions:
            for action in self.actions:
                self._process_action(action)

    def _process_action(self, action: str):
        """Processes action"""
        if action == "call":
            self._call(self.target, self.args, self.kwargs)
            return
        if action == "process_output":
            output = self._call(self.target, self.args, self.kwargs)
            self._call(self.output_processor, (output,))
            return

    def _call(self, target: Callable, args: tuple = None, kwargs: dict = None):
        """Call target function/method

        Returns output if any
        """
        if not callable(target):
            raise ValueError("'target' is not callable")
        if args is None:
            args = ()
        if kwargs is None:
            kwargs = {}
        return target(*args, **kwargs)


class TaskHandler:
    """Handles tasks"""

    tasks = []
    active = False
    _threads: dict[Task, threading.Thread] = {}

    @classmethod
    def start(cls):
        """Start the task handler"""
        cls.active = True
        for task in cls.tasks:
            cls._start_task_thread(task)

    @classmethod
    def stop(cls):
        """Stop the task handler"""
        cls.active = False

    @classmethod
    def _start_task_thread(cls, task: Task):
        """Start the task in a dedicated thread"""
        cls._threads[task] = threading.Thread(target=cls._run, daemon=True)
        cls._threads[task].start()

    @classmethod
    def queue_task(cls, task: Task):
        """Add task to queue"""
        cls.tasks.append(task)
        if cls.active:
            cls._start_task_thread(task)

    @classmethod
    def _run(cls, task: Task):
        """Run task"""
        if not task.repeat:
            task.tick()
            cls.tasks.remove(task)
            return

        # Repeated task
        while cls.active:
            task.tick()
            sleep(task.tick_interval)
