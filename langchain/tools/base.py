"""Base implementation for tools or skills."""

import inspect
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union

from pydantic import BaseModel, Extra, Field, validator

from langchain.callbacks import get_callback_manager
from langchain.callbacks.base import BaseCallbackManager


class ArgInfo(BaseModel):
    name: str
    description: str


class BaseTool(ABC, BaseModel):
    name: str
    description: str
    tool_args: Optional[List[ArgInfo]] = None
    return_direct: bool = False
    verbose: bool = False
    callback_manager: BaseCallbackManager = Field(default_factory=get_callback_manager)

    class Config:
        """Configuration for this pydantic object."""

        extra = Extra.forbid
        arbitrary_types_allowed = True

    @property
    def args(self) -> List[ArgInfo]:
        if self.tool_args is None:
            # Get the name expected in the run function
            var_names = inspect.signature(self._run).parameters.keys()
            return [ArgInfo(name=name, description="") for name in var_names]
        else:
            return self.tool_args

    @validator("callback_manager", pre=True, always=True)
    def set_callback_manager(
        cls, callback_manager: Optional[BaseCallbackManager]
    ) -> BaseCallbackManager:
        """If callback manager is None, set it.

        This allows users to pass in None as callback manager, which is a nice UX.
        """
        return callback_manager or get_callback_manager()

    @abstractmethod
    def _run(self, *args: Any, **kwargs: Any) -> str:
        """Use the tool."""

    @abstractmethod
    async def _arun(self, *args: Any, **kwargs: Any) -> str:
        """Use the tool asynchronously."""

    def run(
        self,
        tool_input: Union[str, Dict],
        verbose: Optional[bool] = None,
        start_color: Optional[str] = "green",
        color: Optional[str] = "green",
        **kwargs: Any
    ) -> str:
        """Run the tool."""
        if isinstance(tool_input, str):
            if len(self.args) > 1:
                raise ValueError("Cannot pass in a string when > 1 argument expected")
            key = self.args[0].name
            run_input = {key: tool_input}
        else:
            run_input = tool_input
        if not self.verbose and verbose is not None:
            verbose_ = verbose
        else:
            verbose_ = self.verbose
        self.callback_manager.on_tool_start(
            {"name": self.name, "description": self.description},
            str(run_input),
            verbose=verbose_,
            color=start_color,
            **kwargs,
        )
        try:
            observation = self._run(**run_input)
        except (Exception, KeyboardInterrupt) as e:
            self.callback_manager.on_tool_error(e, verbose=verbose_)
            raise e
        self.callback_manager.on_tool_end(
            observation, verbose=verbose_, color=color, name=self.name, **kwargs
        )
        return observation

    async def arun(
        self,
        tool_input: Union[str, Dict],
        verbose: Optional[bool] = None,
        start_color: Optional[str] = "green",
        color: Optional[str] = "green",
        **kwargs: Any
    ) -> str:
        """Run the tool asynchronously."""
        if isinstance(tool_input, str):
            if len(self.args) > 1:
                raise ValueError("Cannot pass in a string when > 1 argument expected")
            key = self.args[0].name
            run_input = {key: tool_input}
        else:
            run_input = tool_input
        if not self.verbose and verbose is not None:
            verbose_ = verbose
        else:
            verbose_ = self.verbose
        if self.callback_manager.is_async:
            await self.callback_manager.on_tool_start(
                {"name": self.name, "description": self.description},
                str(run_input),
                verbose=verbose_,
                color=start_color,
                **kwargs,
            )
        else:
            self.callback_manager.on_tool_start(
                {"name": self.name, "description": self.description},
                str(run_input),
                verbose=verbose_,
                color=start_color,
                **kwargs,
            )
        try:
            # We then call the tool on the tool input to get an observation
            observation = await self._arun(**run_input)
        except (Exception, KeyboardInterrupt) as e:
            if self.callback_manager.is_async:
                await self.callback_manager.on_tool_error(e, verbose=verbose_)
            else:
                self.callback_manager.on_tool_error(e, verbose=verbose_)
            raise e
        if self.callback_manager.is_async:
            await self.callback_manager.on_tool_end(
                observation, verbose=verbose_, color=color, name=self.name, **kwargs
            )
        else:
            self.callback_manager.on_tool_end(
                observation, verbose=verbose_, color=color, name=self.name, **kwargs
            )
        return observation

    def __call__(self, tool_input: str) -> str:
        """Make tool callable."""
        return self.run(tool_input)
