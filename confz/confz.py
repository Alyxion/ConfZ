from contextlib import AbstractContextManager
from typing import ClassVar, Type

from pydantic import BaseModel

from .confz_source import ConfZSources
from .exceptions import ConfZException
from .loaders import get_loader


def _load_config(config_kwargs: dict, confz_sources: ConfZSources) -> dict:
    config = config_kwargs.copy()
    if isinstance(confz_sources, list):
        for confz_source in confz_sources:
            loader = get_loader(type(confz_source))
            loader.populate_config(config, confz_source)
    else:
        loader = get_loader(type(confz_sources))
        loader.populate_config(config, confz_sources)
    return config


class ConfZMetaclass(type(BaseModel)):
    """ConfZ Meta Class, inheriting from the pydantic `BaseModel` MetaClass. It would have been cleaner to
    implemented the logic in `__call__` in the ConfZ class itself with `__new__` instead, but pydantic currently
    does not support to overwrite this method."""

    def __call__(cls, config_sources: ConfZSources = None, **kwargs):
        """Called every time an instance of any ConfZ object is created. Injects the config value population and
        singleton mchanism."""
        if config_sources is not None:
            config = _load_config(kwargs, config_sources)
            return super().__call__(**config)

        if cls.CONFIG_SOURCES is not None:
            if len(kwargs) > 0:
                raise ConfZException('Singleton mechanism enabled ("CONFIG_SOURCES" is defined), so keyword arguments '
                                     'are not supported')
            if cls._confz_instance is None:
                config = _load_config(kwargs, cls.CONFIG_SOURCES)
                cls._confz_instance = super().__call__(**config)
            return cls._confz_instance

        return super().__call__(**kwargs)


class SourceChangeManager(AbstractContextManager):
    """Config sources change context manager, allows to change config sources within a controlled context and resets
    everything afterwards."""

    def __init__(self, config_class: Type['ConfZ'], config_sources: ConfZSources):
        self._config_class = config_class
        self._config_sources = config_sources
        self._backup_instance = None
        self._backup_sources = None

    def __enter__(self):
        self._backup_instance = self._config_class._confz_instance
        self._config_class._confz_instance = None

        self._backup_sources = self._config_class.CONFIG_SOURCES
        self._config_class.CONFIG_SOURCES = self._config_sources
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        self._config_class._confz_instance = self._backup_instance
        self._config_class.CONFIG_SOURCES = self._backup_sources


class ConfZ(BaseModel, metaclass=ConfZMetaclass):
    """ConfZ Base Class, parent of every config class. Internally wraps the pydantic `BaseModel` class and behaves
    transparent except for two cases:
    - If the constructor gets `config_source` as kwarg, it is used to enrich the other kwargs with the sources
    defined in the `ConfZSource` object (files, env-vars, commandline args).
    - If the config class has the class variable `CONFIG_SOURCE` defined, it is used to to enrich the existing kwargs
    with the sources defined in the `ConfZSource` object as above. Additionally, a singleton mechanism is in place
    for this case, returning the same config class instance every time the constructor is called.
    Additionally, the object is faux-immutable per default."""

    CONFIG_SOURCES: ClassVar[ConfZSources] = None
    _confz_instance: ClassVar['ConfZ'] = None

    class Config:
        allow_mutation = False

    @classmethod
    def change_config_sources(cls, config_sources: ConfZSources):
        """Change the config sources class variable within a controlled context. Within this context, the sources
        will be different and the singleton reset, if it existed. This can be useful in unit tests to temporarily
        change a configuration.
        :param config_sources: The temporary config sources for within the context.
        """
        return SourceChangeManager(cls, config_sources)
