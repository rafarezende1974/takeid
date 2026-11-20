"""Testes do motor DX Rename — sem fotos reais, sem tela.

Rode:  python3 test_engine.py
Cria arquivos temporarios (JPG de verdade via Pillow, RAW/video
como arquivos vazios com a extensao certa) e confere o motor.
"""
import os
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from rename_engine import (  # noqa: E402
    Settings, apply_plan, build_plan, get_photo_datetime,
    has_conflicts, load_last_log, undo_last_batch,
)


def make_jpg(path, exif_dt=None):
    from PIL import Image
    img = Image.new("RGB", (8, 8), (200, 30, 90))
    if exif_dt:
        exif = Image.Exif()
        exif[36867] = exif_dt  # DateTimeOriginal
        img.save(path, exif=exif)
    else:
        img.save(path)


def touch(path, content=b"x"):
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_bytes(content)


class EngineTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.dir = Path(self.tmp.name)
        self.log = self.dir / "log"

    def tearDown(self):
        self.tmp.cleanup()

    def files(self, *names):
        out = []
        for name in names:
            p = self.dir / name
            if p.suffix.lower() in (".jpg", ".jpeg"):
                make_jpg(p)
            else:
                touch(p)
            out.append(p)
        return out

    def test_pareamento_jpg_raw_mesmo_numero(self):
        paths = self.files("DSC001.JPG", "DSC001.ARW", "DSC002.JPG",
                           "DSC002.NEF")
        plan = build_plan(paths, Settings())
        self.assertFalse(has_conflicts(plan), [e.error for e in plan])
        names = [e.new_name for e in plan]
        self.assertEqual(names, [
            "EXPO2026_FOTO_0001.JPG", "EXPO2026_FOTO_0001.ARW",
            "EXPO2026_FOTO_0002.JPG", "EXPO2026_FOTO_0002.NEF",
        ])

    def test_contadores_separados_foto_video(self):
        paths = self.files("DSC001.JPG", "C0001.MP4", "DSC002.JPG",
                           "C0002.MP4")
        plan = build_plan(paths, Settings())
        names = [e.new_name for e in plan]
        self.assertEqual(names, [
            "EXPO2026_FOTO_0001.JPG", "EXPO2026_TAKE_0001.MP4",
            "EXPO2026_FOTO_0002.JPG", "EXPO2026_TAKE_0002.MP4",
        ])

    def test_inicio_125_e_20(self):
        paths = self.files("DSC001.JPG", "C0001.MP4")
        plan = build_plan(paths, Settings(inicio_fotos=125,
                                          inicio_videos=20))
        self.assertEqual([e.new_name for e in plan], [
            "EXPO2026_FOTO_0125.JPG", "EXPO2026_TAKE_0020.MP4",
        ])

    def test_tipo_video_configuravel(self):
        paths = self.files("C0001.MP4")
        plan = build_plan(paths, Settings(tipo_video="VIDEO"))
        self.assertEqual(plan[0].new_name, "EXPO2026_VIDEO_0001.MP4")

    def test_conflito_duplicado_sem_seq(self):
        paths = self.files("DSC001.JPG", "DSC002.JPG")
        plan = build_plan(paths, Settings(pattern="{evento}_{tipo}"))
        self.assertTrue(has_conflicts(plan))
        self.assertTrue(all(e.error and "duplicado" in e.error
                            for e in plan))

    def test_destino_ja_existe_fora_do_lote(self):
        self.files("EXPO2026_FOTO_0001.JPG")
        paths = self.files("DSC001.JPG")
        plan = build_plan(paths, Settings())
        self.assertTrue(has_conflicts(plan))
        self.assertIn("já existe", plan[0].error)

    def test_nome_invalido_e_reservado(self):
        paths = self.files("DSC001.JPG", "DSC002.JPG")
        bad = build_plan(paths, Settings(pattern="{evento}:FOTO_{seq:0000}"))
        self.assertIn("inválido", bad[0].error)
        reserved = build_plan(
            paths, Settings(pattern="CON", evento=""))
        self.assertIn("reservado", reserved[0].error)

    def test_variavel_desconhecida_e_nome_longo(self):
        paths = self.files("DSC001.JPG")
        unknown = build_plan(paths, Settings(pattern="{evento}_{foo}"))
        self.assertIn("desconhecida", unknown[0].error)
        long_plan = build_plan(
            paths, Settings(pattern="A" * 250 + "_{seq:0000}"))
        self.assertIn("240", long_plan[0].error)

    def test_troca_a_para_b_e_b_para_a(self):
        paths = self.files("AAA.JPG", "BBB.JPG")
        plan = build_plan(paths, Settings(
            pattern="{nome}", evento=""))
        # Forca a troca manual: AAA->BBB, BBB->AAA (padrao nao faz
        # isso sozinho; simula dois destinos trocados).
        plan[0].new_name, plan[1].new_name = "BBB.JPG", "AAA.JPG"
        plan[0].new_path = self.dir / "BBB.JPG"
        plan[1].new_path = self.dir / "AAA.JPG"
        plan[0].no_change = plan[1].no_change = False
        result = apply_plan(plan, self.log)
        self.assertEqual(result["erros"], [])
        self.assertEqual(result["renomeados"], 2)
        self.assertTrue((self.dir / "AAA.JPG").exists())
        self.assertTrue((self.dir / "BBB.JPG").exists())

    def test_aplicar_e_desfazer_restaura_originais(self):
        paths = self.files("DSC001.JPG", "DSC001.ARW", "C0001.MP4")
        plan = build_plan(paths, Settings())
        result = apply_plan(plan, self.log)
        self.assertEqual(result["renomeados"], 3)
        self.assertEqual(result["erros"], [])
        self.assertTrue((self.dir / "EXPO2026_FOTO_0001.JPG").exists())
        self.assertTrue(load_last_log(self.log))
        undo = undo_last_batch(self.log)
        self.assertEqual(undo["erros"], [])
        self.assertEqual(undo["restaurados"], 3)
        self.assertTrue((self.dir / "DSC001.JPG").exists())
        self.assertTrue((self.dir / "DSC001.ARW").exists())
        self.assertTrue((self.dir / "C0001.MP4").exists())
        self.assertFalse((self.dir / "EXPO2026_FOTO_0001.JPG").exists())
        # Desfazer de novo nao tem o que fazer.
        self.assertEqual(undo_last_batch(self.log)["restaurados"], 0)

    def test_exif_lido_e_fallback_data_modificacao(self):
        jpg_exif = self.dir / "COM_EXIF.JPG"
        make_jpg(jpg_exif, "2021:05:02 10:20:30")
        dt, has = get_photo_datetime(jpg_exif)
        self.assertTrue(has)
        self.assertEqual((dt.year, dt.month, dt.day), (2021, 5, 2))
        jpg_sem = self.dir / "SEM_EXIF.JPG"
        make_jpg(jpg_sem)
        stamp = datetime(2023, 3, 4, 5, 6, 7).timestamp()
        os.utime(jpg_sem, (stamp, stamp))
        dt2, has2 = get_photo_datetime(jpg_sem)
        self.assertFalse(has2)
        self.assertEqual((dt2.year, dt2.month, dt2.day), (2023, 3, 4))
        # {datafoto} usa o EXIF quando existe.
        plan = build_plan([jpg_exif], Settings(
            pattern="{datafoto}_{seq:03}"))
        self.assertEqual(plan[0].new_name, "2021-05-02_001.JPG")

    def test_maiusculas_e_espacos_e_outros_tipos(self):
        paths = self.files("foto teste.png", "DSC001.JPG")
        plan = build_plan(paths, Settings(
            pattern="{evento} {nome} {seq:0000}",
            maiusculas=True, substituir_espacos=True))
        self.assertEqual(plan[0].new_name, "EXPO2026_FOTO_TESTE_0001.png")
        self.assertEqual(plan[0].tipo, "ARQUIVO")
        # Contadores separados: o primeiro FOTO tambem e 0001.
        self.assertEqual(plan[1].new_name, "EXPO2026_DSC001_0001.JPG")

    def test_sem_pareamento_cada_arquivo_tem_numero(self):
        paths = self.files("DSC001.JPG", "DSC001.ARW")
        plan = build_plan(paths, Settings(parear_raw_jpg=False))
        self.assertEqual([e.new_name for e in plan], [
            "EXPO2026_FOTO_0001.JPG", "EXPO2026_FOTO_0002.ARW",
        ])

    def test_nome_igual_ao_atual_nao_bloqueia(self):
        paths = self.files("EXPO2026_FOTO_0001.JPG", "DSC001.JPG")
        plan = build_plan(paths, Settings())
        self.assertFalse(has_conflicts(plan))
        self.assertTrue(plan[0].no_change)
        result = apply_plan(plan, self.log)
        self.assertEqual(result["renomeados"], 1)
        self.assertEqual(result["pulados"], 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
