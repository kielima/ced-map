"""Testes para geocode_banco.clean_entity_name — limpeza de nomes de jurisdições."""

import sys
from pathlib import Path

# Adicionar diretório build/ ao sys.path para importar o módulo
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from geocode_banco import clean_entity_name


class TestCleanEntityName:
    def test_strip_japanese_kanji_parentheses(self):
        assert clean_entity_name("Agematsu Town (上松町)") == "Agematsu"
        assert clean_entity_name("Aso City (阿蘇市)") == "Aso"

    def test_strip_korean_hangul_parentheses(self):
        assert clean_entity_name("Chungcheongnam-do Province (충남도)") == "Chungcheongnam-do"

    def test_strip_korean_with_comma(self):
        assert clean_entity_name("Buk-gu (부산 북구), Busan") == "Buk-gu"

    def test_strip_council_suffixes(self):
        assert clean_entity_name("Acri City Council") == "Acri"
        assert clean_entity_name("Toronto City Council") == "Toronto"
        assert clean_entity_name("Berkeley Borough Council") == "Berkeley"

    def test_strip_us_town_meeting(self):
        assert clean_entity_name("Acton Town Meeting") == "Acton"
        assert clean_entity_name("Buffalo Common Meeting") == "Buffalo"

    def test_strip_county_board_of_commissioners(self):
        assert clean_entity_name("Kalamazoo County Board of Commissioners") == "Kalamazoo"

    def test_strip_prefix_city_of(self):
        assert clean_entity_name("City of Berkeley Council") == "Berkeley"

    def test_strip_compound_japanese(self):
        assert clean_entity_name("Hakuba Village Council (白馬村)") == "Hakuba"

    def test_keeps_name_when_no_suffix(self):
        assert clean_entity_name("Paris") == "Paris"
        assert clean_entity_name("Acri") == "Acri"

    def test_empty_string_safe(self):
        assert clean_entity_name("") == ""

    def test_only_suffix_returns_original(self):
        # Se sobrar nada após limpeza, retorna o original
        assert clean_entity_name("Council") == "Council"
