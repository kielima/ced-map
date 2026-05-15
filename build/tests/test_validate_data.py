"""Testes para validate_data.py — sanity checks do banco.json."""

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO / "build"))

from validate_data import VALID_NIVEIS, VALID_CORES, REQUIRED_FIELDS


class TestBancoJsonIntegrity:
    @classmethod
    def setup_class(cls):
        with open(REPO / "data" / "banco.json", encoding="utf-8") as f:
            cls.banco = json.load(f)

    def test_is_non_empty_list(self):
        assert isinstance(self.banco, list)
        assert len(self.banco) > 100, "Esperado pelo menos 100 entradas"

    def test_first_entry_has_required_fields(self):
        missing = REQUIRED_FIELDS - set(self.banco[0].keys())
        assert not missing, f"Campos em falta: {missing}"

    def test_all_niveis_valid(self):
        niveis = {e.get("nivel") for e in self.banco}
        invalid = niveis - VALID_NIVEIS
        assert not invalid, f"Níveis inválidos: {invalid}"

    def test_all_cores_valid(self):
        cores = {e.get("cor_mapa") for e in self.banco}
        invalid = cores - VALID_CORES
        assert not invalid, f"Cores inválidas: {invalid}"

    def test_iso_3_format(self):
        # Sempre que iso_3 está presente, deve ter 2 ou 3 caracteres (EU=2, USA=3)
        for e in self.banco:
            iso = e.get("iso_3")
            if iso:
                assert len(iso) in (2, 3), f"ISO inesperado: {iso!r}"
                assert iso.isupper(), f"ISO deve ser maiúsculo: {iso!r}"

    def test_lat_lon_consistency(self):
        # Se uma entrada tem lat, deve ter lon, e vice-versa
        for e in self.banco:
            has_lat = e.get("lat") is not None
            has_lon = e.get("lon") is not None
            assert has_lat == has_lon, f"lat/lon inconsistente em {e.get('entidade')}"

    def test_lat_lon_in_range(self):
        for e in self.banco:
            lat = e.get("lat")
            lon = e.get("lon")
            if lat is not None:
                assert -90 <= lat <= 90, f"lat fora do intervalo em {e.get('entidade')}: {lat}"
                assert -180 <= lon <= 180, f"lon fora do intervalo em {e.get('entidade')}: {lon}"
