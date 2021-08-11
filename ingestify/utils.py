import abc
import inspect
import time
from datetime import datetime, timezone
from string import Template
from typing import Generic, Type, TypeVar, Dict


class ComponentRegistry:
    def __init__(self):
        self.__registered_components = {}

        class _Registered(abc.ABCMeta):
            def __new__(mcs, cls_name, bases, class_dict):
                class_dict["name"] = cls_name
                component_cls = super(_Registered, mcs).__new__(
                    mcs, cls_name, bases, class_dict
                )
                if not inspect.isabstract(component_cls):
                    self.register_component(cls_name, component_cls)
                return component_cls

        self.__metaclass = _Registered

    @property
    def metaclass(self):
        return self.__metaclass

    def register_component(self, cls_name, component_cls):
        self.__registered_components[cls_name] = component_cls

    def get_component(self, cls_name: str):
        return self.__registered_components[cls_name]


T = TypeVar("T")
R = TypeVar("R")


class ComponentFactory(Generic[T]):
    def __init__(self, registry: ComponentRegistry):
        self.registry = registry

    @classmethod
    def build_factory(
        cls, component_cls: Type[R], registry: ComponentRegistry
    ) -> "ComponentFactory[R]":
        return cls[component_cls](registry)

    def build(self, cls_name, **kwargs) -> T:
        component_cls = self.registry.get_component(cls_name)
        try:
            return component_cls.from_dict(**kwargs)
        except AttributeError:
            pass
        try:
            return component_cls(**kwargs)
        except TypeError as e:
            raise e
            # raise TypeError(f"Could not initialize {cls_name}")


def key_from_dict(d: dict) -> str:
    return "/".join([f"{k}={v}" for k, v in sorted(d.items()) if not k.startswith("_")])


def utcnow() -> datetime:
    return datetime.fromtimestamp(time.time(), timezone.utc)


class AttributeBag:
    def __init__(self, **kwargs):
        self.attributes = kwargs
        self.key = key_from_dict(self.attributes)

    def __getattr__(self, item):
        if item in self.__dict__:
            return self.__dict__[item]
        if "attributes" in self.__dict__ and item in self.attributes:
            return self.attributes[item]
        raise AttributeError

    def format_string(self, string: str):
        return Template(string).substitute(**self.attributes)

    def matches(self, attributes: Dict) -> bool:
        for k, v in self.attributes.items():
            if attributes.get(k) != v:
                return False
        return True

    @property
    def filtered_attributes(self):
        return {k: v for k, v in self.attributes.items() if not k.startswith("_")}

    def __hash__(self):
        return hash(self.key)

    def __repr__(self):
        return f"{self.__class__.__name__}({', '.join([f'{k}={v}' for k, v in self.filtered_attributes.items()])})"

    @classmethod
    def create_from(cls, other: 'AttributeBag', **kwargs):
        _args = dict(**other.attributes)
        _args.update(kwargs)

        return cls(
            **_args
        )
