"""
Character Card Models

Defines the data structures for Character Card versions 1, 2, and 3.
Provides a unified interface to read/write properties transparently.
"""

from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field


class CharacterCard:
    """Base class for all Character Card versions."""
    
    @property
    def version(self) -> int:
        raise NotImplementedError()
        
    @property
    def raw_data(self) -> Dict[str, Any]:
        """Provides access to the raw internal dictionary for backwards-compatibility or direct access."""
        raise NotImplementedError()

    @property
    def name(self) -> str:
        raise NotImplementedError()
        
    @property
    def display_name(self) -> str:
        """Returns the best available name for display (e.g. nickname in V3, falling back to name)."""
        return self.name

    @property
    def description(self) -> str:
        raise NotImplementedError()

    @property
    def personality(self) -> str:
        raise NotImplementedError()
        
    @property
    def scenario(self) -> str:
        raise NotImplementedError()

    @property
    def first_mes(self) -> str:
        raise NotImplementedError()
        
    @property
    def mes_example(self) -> str:
        raise NotImplementedError()

    @property
    def alternate_greetings(self) -> List[str]:
        return []

    def get_greeting(self, index: int = 0) -> str:
        """Get greeting by index (0 is first_mes, 1+ is alternate_greetings)."""
        if index == 0:
            return self.first_mes
        if 0 < index <= len(self.alternate_greetings):
            return self.alternate_greetings[index - 1]
        return self.first_mes

    def to_dict(self) -> Dict[str, Any]:
        """Serialize back to original dictionary format."""
        raise NotImplementedError()


@dataclass
class CharacterCardV1(CharacterCard):
    """
    Character Card V1 implementation.
    Data is stored flat, without 'data' or 'spec' fields.
    """
    _name: str = ""
    _description: str = ""
    _personality: str = ""
    _scenario: str = ""
    _first_mes: str = ""
    _mes_example: str = ""

    @property
    def version(self) -> int:
        return 1
        
    @property
    def name(self) -> str: return self._name
    
    @property
    def description(self) -> str: return self._description
    
    @property
    def personality(self) -> str: return self._personality
    
    @property
    def scenario(self) -> str: return self._scenario
    
    @property
    def first_mes(self) -> str: return self._first_mes
    
    @property
    def mes_example(self) -> str: return self._mes_example

    @property
    def raw_data(self) -> Dict[str, Any]:
        return {
            "name": self._name,
            "description": self._description,
            "personality": self._personality,
            "scenario": self._scenario,
            "first_mes": self._first_mes,
            "mes_example": self._mes_example
        }

    def to_dict(self) -> Dict[str, Any]:
        return self.raw_data
        
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CharacterCardV1':
        return cls(
            _name=data.get("name", ""),
            _description=data.get("description", ""),
            _personality=data.get("personality", ""),
            _scenario=data.get("scenario", ""),
            _first_mes=data.get("first_mes", ""),
            _mes_example=data.get("mes_example", "")
        )


@dataclass
class CharacterCardV2(CharacterCard):
    """
    Character Card V2 implementation.
    Data is wrapped inside a 'data' field.
    """
    spec: str = "chara_card_v2"
    spec_version: str = "2.0"
    
    _data: Dict[str, Any] = field(default_factory=dict)

    @property
    def version(self) -> int:
        return 2

    @property
    def raw_data(self) -> Dict[str, Any]:
        return self._data
        
    @property
    def name(self) -> str: return self._data.get("name", "")
    
    @property
    def description(self) -> str: return self._data.get("description", "")
    
    @property
    def personality(self) -> str: return self._data.get("personality", "")
    
    @property
    def scenario(self) -> str: return self._data.get("scenario", "")
    
    @property
    def first_mes(self) -> str: return self._data.get("first_mes", "")
    
    @property
    def mes_example(self) -> str: return self._data.get("mes_example", "")
    
    @property
    def alternate_greetings(self) -> List[str]:
        return self._data.get("alternate_greetings", [])

    def to_dict(self) -> Dict[str, Any]:
        return {
            "spec": self.spec,
            "spec_version": self.spec_version,
            "data": self._data
        }
        
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CharacterCardV2':
        return cls(
            spec=data.get("spec", "chara_card_v2"),
            spec_version=data.get("spec_version", "2.0"),
            _data=data.get("data", {})
        )


@dataclass
class CharacterCardV3(CharacterCard):
    """
    Character Card V3 implementation.
    Data is wrapped inside a 'data' field and supports newer spec fields (like assets, nickname).
    """
    spec: str = "chara_card_v3"
    spec_version: str = "3.0"
    
    _data: Dict[str, Any] = field(default_factory=dict)

    @property
    def version(self) -> int:
        return 3

    @property
    def raw_data(self) -> Dict[str, Any]:
        return self._data

    @property
    def name(self) -> str: return self._data.get("name", "")
    
    @property
    def nickname(self) -> str: return self._data.get("nickname")
    
    @property
    def display_name(self) -> str: 
        return self.nickname if self.nickname else self.name
        
    @property
    def description(self) -> str: return self._data.get("description", "")
    
    @property
    def personality(self) -> str: return self._data.get("personality", "")
    
    @property
    def scenario(self) -> str: return self._data.get("scenario", "")
    
    @property
    def first_mes(self) -> str: return self._data.get("first_mes", "")
    
    @property
    def mes_example(self) -> str: return self._data.get("mes_example", "")
    
    @property
    def alternate_greetings(self) -> List[str]:
        return self._data.get("alternate_greetings", [])
        
    @property
    def assets(self) -> List[Dict[str, str]]:
        return self._data.get("assets", [])

    def to_dict(self) -> Dict[str, Any]:
        return {
            "spec": self.spec,
            "spec_version": self.spec_version,
            "data": self._data
        }
        
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'CharacterCardV3':
        return cls(
            spec=data.get("spec", "chara_card_v3"),
            spec_version=data.get("spec_version", "3.0"),
            _data=data.get("data", {})
        )
