import unittest
from src.filtro import Filtro

class TestPresenciaHistorica(unittest.TestCase):
    def test_scoring_presencia_historica_incoop(self):
        filtro = Filtro()
        
        # 1. Licitación en municipio histórico (Solsona)
        lic_solsona = {
            "titulo": "Gestió i dinamització del casal de joves de Solsona",
            "organo": "Ajuntament de Solsona",
            "localidad": "Solsona",
            "importe": 120000.0,
            "vec": 240000.0,
            "tipo_contrato_codigo": "2",
            "estado": "PUB",
            "cpvs": ["80400000"],
            "fecha_limite": "2030-12-31 23:59:59"
        }
        res_solsona = filtro.filtrar(lic_solsona)
        self.assertTrue(res_solsona["apta"])
        self.assertTrue(any("Presencia Histórica/Operativa Directa Incoop" in m for m in res_solsona["motivos"]))
        self.assertTrue(any("+40" in m for m in res_solsona["motivos"] if "Presencia Histórica" in m))

        # 2. Licitación en ente específico histórico (Consorci de la Mina)
        lic_mina = {
            "titulo": "Servei d'atenció comunitària i dinamització social",
            "organo": "Consorci de la Mina",
            "localidad": "Sant Adrià de Besòs",
            "importe": 150000.0,
            "vec": 300000.0,
            "tipo_contrato_codigo": "2",
            "estado": "PUB",
            "cpvs": ["85320000"],
            "fecha_limite": "2030-12-31 23:59:59"
        }
        res_mina = filtro.filtrar(lic_mina)
        self.assertTrue(res_mina["apta"])
        self.assertTrue(any("Presencia Histórica/Operativa Directa Incoop" in m for m in res_mina["motivos"]))

        # 3. Licitación en barrio histórico de Barcelona (Sant Martí)
        lic_sant_marti = {
            "titulo": "Servei de neteja i manteniment d'escola bressol a Sant Martí",
            "organo": "Ajuntament de Barcelona",
            "localidad": "Barcelona",
            "importe": 90000.0,
            "vec": 180000.0,
            "tipo_contrato_codigo": "2",
            "estado": "PUB",
            "cpvs": ["80110000"],
            "fecha_limite": "2030-12-31 23:59:59"
        }
        res_sant_marti = filtro.filtrar(lic_sant_marti)
        self.assertTrue(res_sant_marti["apta"])
        self.assertTrue(any("Presencia Histórica/Operativa Directa Incoop" in m for m in res_sant_marti["motivos"]))

if __name__ == "__main__":
    unittest.main()

