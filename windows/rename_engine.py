"""TakeID 1.0.0 by DX Labs — motor de renomeacao em lote (Windows).

Motor puro, sem Tkinter e sem dependencia de tela: classifica arquivos,
pareia JPG+RAW, calcula sequencias, monta nomes a partir de um padrao
com tokens, valida conflitos e aplica o lote com seguranca.

Regras duras (do plano DX Rename / manual TakeID):
  * nada e renomeado sem preview — este motor so calcula o plano;
    a aplicacao so acontece em apply_plan(), depois da confirmacao.
  * conflitos BLOQUEIAM o lote: duplicado, destino existente,
    caractere invalido, nome reservado do Windows, nome > 240 chars,
    variavel desconhecida no padrao.
  * nunca sobrescreve: destino existente fora do lote e conflito.
  * trocas de nome (A -> B e B -> A no mesmo lote) sao feitas em duas
    passadas com nomes temporarios, para nao haver colisao.
  * cada lote aplicado grava um log de -> para (JSON + CSV) que o
    Desfazer usa para restaurar os originais, mesmo apos fechar
    e reabrir o app.
"""
from __future__ import annotations

import csv
import json
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

__version__ = "1.0.0"

# ---------------------------------------------------------------- tipos

JPG_EXTS = {".jpg", ".jpeg"}
RAW_EXTS = {
    ".raw", ".arw", ".cr2", ".cr3", ".nef", ".nrw", ".dng",
    ".raf", ".rw2", ".orf", ".pef", ".srw", ".3fr", ".iiq",
}
VIDEO_EXTS = {
    ".mp4", ".mov", ".mxf", ".avi", ".mkv",
    ".mts", ".m2ts", ".m4v", ".webm",
}

# JPG e RAW sao "fotos" (mesmo contador, pareamento). Video tem o
# proprio contador. O resto e ARQUIVO, com contador proprio.
KIND_PHOTO = "FOTO"
KIND_VIDEO = "VIDEO"
KIND_OTHER = "ARQUIVO"

INVALID_CHARS = set('<>:"/\\|?*')
RESERVED_NAMES = {
    "CON", "PRN", "AUX", "NUL",
    *(f"COM{i}" for i in range(1, 10)),
    *(f"LPT{i}" for i in range(1, 10)),
}
MAX_NAME_LEN = 240  # limite do motor (manual TakeID); Windows: 255

TOKEN_RE = re.compile(r"\{([^{}]+)\}")
SIMPLE_TOKENS = {
    "evento", "tipo", "nome", "original", "data", "datafoto",
    "hora", "cliente", "ext", "pasta",
}


def classify(path) -> str:
    """JPG | RAW | VIDEO | ARQUIVO, pela extensao (minuscula)."""
    ext = Path(path).suffix.lower()
    if ext in JPG_EXTS:
        return "JPG"
    if ext in RAW_EXTS:
        return "RAW"
    if ext in VIDEO_EXTS:
        return "VIDEO"
    return "ARQUIVO"


def kind_of(classification: str) -> str:
    if classification in ("JPG", "RAW"):
        return KIND_PHOTO
    if classification == "VIDEO":
        return KIND_VIDEO
    return KIND_OTHER


# ---------------------------------------------------------------- EXIF

def _parse_exif_datetime(value):
    """'2026:11:18 14:30:22' -> datetime | None."""
    if not value:
        return None
    if isinstance(value, bytes):
        value = value.decode("utf-8", "ignore")
    value = str(value).strip()
    for fmt in ("%Y:%m:%d %H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y:%m:%d"):
        try:
            return datetime.strptime(value, fmt)
        except ValueError:
            continue
    return None


def get_photo_datetime(path):
    """(datetime, tem_exif).

    Tenta DateTimeOriginal (36867) e DateTime (306) do EXIF do JPG.
    Sem EXIF (RAW sem metadado legivel, video, PNG, print...), usa a
    data de modificacao do arquivo e tem_exif=False — o app mostra o
    selo "sem EXIF" nesse caso.
    """
    path = Path(path)
    dt = None
    try:
        from PIL import Image

        with Image.open(path) as img:
            exif = img.getexif()
            if exif:
                dt = _parse_exif_datetime(exif.get(36867))
                if dt is None:
                    dt = _parse_exif_datetime(exif.get(306))
    except Exception:
        dt = None
    if dt is not None:
        return dt, True
    try:
        return datetime.fromtimestamp(path.stat().st_mtime), False
    except OSError:
        return None, False


# ---------------------------------------------------------------- config

@dataclass
class Settings:
    pattern: str = "{evento}_{tipo}_{seq:0000}"
    evento: str = "EXPO2026"
    cliente: str = ""
    tipo_foto: str = "FOTO"      # configuravel; padrao TakeID
    tipo_video: str = "TAKE"     # mockup usa TAKE; manual usava VIDEO
    tipo_arquivo: str = "ARQUIVO"
    inicio_fotos: int = 1
    inicio_videos: int = 1
    inicio_arquivos: int | None = None  # None = comeca no inicio_fotos
    formato_data: str = "%Y-%m-%d"     # {data} e {datafoto}
    maiusculas: bool = False
    substituir_espacos: bool = False
    usar_data_arquivo: bool = True
    parear_raw_jpg: bool = True

    def to_dict(self):
        return {
            "pattern": self.pattern, "evento": self.evento,
            "cliente": self.cliente, "tipo_foto": self.tipo_foto,
            "tipo_video": self.tipo_video,
            "tipo_arquivo": self.tipo_arquivo,
            "inicio_fotos": self.inicio_fotos,
            "inicio_videos": self.inicio_videos,
            "inicio_arquivos": self.inicio_arquivos,
            "formato_data": self.formato_data,
            "maiusculas": self.maiusculas,
            "substituir_espacos": self.substituir_espacos,
            "usar_data_arquivo": self.usar_data_arquivo,
            "parear_raw_jpg": self.parear_raw_jpg,
        }

    @classmethod
    def from_dict(cls, data):
        known = {f.name for f in cls.__dataclass_fields__.values()}
        return cls(**{k: v for k, v in (data or {}).items() if k in known})


@dataclass
class PlanEntry:
    original_path: Path
    new_name: str = ""
    new_path: Path | None = None
    kind: str = "ARQUIVO"          # JPG | RAW | VIDEO | ARQUIVO
    tipo: str = "ARQUIVO"          # FOTO | TAKE | ARQUIVO (rotulo)
    seq: int = 0
    error: str | None = None
    no_change: bool = False        # novo nome == nome atual
    has_exif: bool = False
    photo_datetime: datetime | None = None

    @property
    def original_name(self):
        return self.original_path.name

    @property
    def ok(self):
        return self.error is None


# ---------------------------------------------------------------- padrao

def _seq_width(spec: str):
    """Largura de {seq:0000} / {seq:03} / {seq:6}.

    '0000' -> 4 (zeros = largura minima, nao corta numeros maiores);
    '03'   -> 3; '6' -> 6. Qualquer outra coisa -> None (invalido).
    """
    if not spec:
        return None
    if set(spec) == {"0"}:
        return len(spec)
    if spec.isdigit():
        return int(spec)
    return None


def render_pattern(pattern: str, values: dict, seq: int):
    """Monta o nome-base. Retorna (nome, erro|None)."""
    def repl(match):
        token = match.group(1)
        if token == "seq":
            return f"{seq:04d}"
        if token.startswith("seq:"):
            width = _seq_width(token[4:])
            if width is None:
                raise ValueError(f"Sequência inválida: {{{token}}}")
            return str(seq).zfill(width)
        if token in SIMPLE_TOKENS:
            return str(values.get(token, ""))
        raise ValueError(f"Variável desconhecida: {{{token}}}")

    try:
        return TOKEN_RE.sub(repl, pattern), None
    except ValueError as exc:
        return "", str(exc)


# ---------------------------------------------------------------- plano

def build_plan(paths, settings: Settings) -> list[PlanEntry]:
    """Calcula o preview Original -> Novo, na ordem recebida.

    A ordem da lista define a numeracao. Pares JPG+RAW (mesmo
    nome-base, mesma pasta, sem diferenciar maiusculas) recebem o
    MESMO numero sequencial quando settings.parear_raw_jpg=True.
    Fotos e videos tem contadores separados.
    """
    paths = [Path(p) for p in paths]
    entries: list[PlanEntry] = []
    photo_next = int(settings.inicio_fotos)
    video_next = int(settings.inicio_videos)
    other_next = int(settings.inicio_arquivos
                     if settings.inicio_arquivos is not None
                     else settings.inicio_fotos)
    photo_groups: dict[tuple, int] = {}
    group_first_name: dict[tuple, str] = {}
    now = datetime.now()

    for path in paths:
        classification = classify(path)
        kind = kind_of(classification)
        base = path.stem
        ext = path.suffix  # mantem a caixa original (.jpg fica .jpg)
        dt, has_exif = get_photo_datetime(path)
        ref_dt = dt if (settings.usar_data_arquivo and dt) else now
        datafoto_dt = dt if has_exif else ref_dt

        if kind == KIND_PHOTO:
            tipo = settings.tipo_foto
            if settings.parear_raw_jpg:
                key = (str(path.parent).lower(), base.lower())
                if key not in photo_groups:
                    photo_groups[key] = photo_next
                    group_first_name[key] = base
                    photo_next += 1
                seq = photo_groups[key]
                nome_token = group_first_name[key]
            else:
                seq = photo_next
                photo_next += 1
                nome_token = base
        elif kind == KIND_VIDEO:
            tipo = settings.tipo_video
            seq = video_next
            video_next += 1
            nome_token = base
        else:
            tipo = settings.tipo_arquivo
            seq = other_next
            other_next += 1
            nome_token = base

        values = {
            "evento": settings.evento,
            "tipo": tipo,
            "nome": nome_token,
            "original": nome_token,
            "data": ref_dt.strftime(settings.formato_data),
            "datafoto": datafoto_dt.strftime(settings.formato_data),
            "hora": ref_dt.strftime("%H%M%S"),
            "cliente": settings.cliente,
            "ext": ext.lstrip("."),
            "pasta": path.parent.name,
        }
        new_base, error = render_pattern(settings.pattern, values, seq)
        if error is None:
            if settings.substituir_espacos:
                new_base = re.sub(r"\s+", "_", new_base)
            if settings.maiusculas:
                new_base = new_base.upper()
        new_name = (new_base + ext) if error is None else ""
        entries.append(PlanEntry(
            original_path=path, new_name=new_name,
            new_path=(path.parent / new_name) if new_name else None,
            kind=classification, tipo=tipo, seq=seq, error=error,
            has_exif=has_exif, photo_datetime=dt,
        ))

    _validate(entries)
    return entries


def _validate(entries: list[PlanEntry]) -> None:
    originals = {str(e.original_path).lower() for e in entries}
    # Duplicado no lote: mesmo destino (pasta + nome, sem caixa).
    dest_count: dict[tuple, int] = {}
    for e in entries:
        if e.new_path is not None and e.error is None:
            key = (str(e.new_path.parent).lower(), e.new_name.lower())
            dest_count[key] = dest_count.get(key, 0) + 1
    for e in entries:
        if e.error is not None:
            continue
        if not e.original_path.exists():
            e.error = "Arquivo de origem não encontrado"
            continue
        if not e.new_name:
            e.error = "Nome vazio"
            continue
        if e.new_name == e.original_name:
            e.no_change = True
            continue
        stem = Path(e.new_name).stem
        if any(ch in INVALID_CHARS for ch in e.new_name):
            e.error = "Caractere inválido no Windows (< > : \" / \\ | ? *)"
            continue
        if stem.upper() in RESERVED_NAMES:
            e.error = f"Nome reservado do Windows: {stem}"
            continue
        if len(e.new_name) > MAX_NAME_LEN:
            e.error = f"Nome com mais de {MAX_NAME_LEN} caracteres"
            continue
        key = (str(e.new_path.parent).lower(), e.new_name.lower())
        if dest_count.get(key, 0) > 1:
            e.error = "Nome duplicado no lote"
            continue
        if e.new_path.exists() and str(e.new_path).lower() not in originals:
            e.error = "Destino já existe" + (
                " (é uma pasta)" if e.new_path.is_dir() else "")
            continue


def has_conflicts(plan) -> bool:
    return any(e.error for e in plan)


def count_conflicts(plan) -> int:
    return sum(1 for e in plan if e.error)


# ---------------------------------------------------------------- aplicar

def _rename_two_pass(pairs, log_dir=None):
    """pairs: [(origem Path, destino Path)].

    Passada 1: origem -> nome temporario unico na mesma pasta.
    Passada 2: temporario -> destino final.
    Se falhar no meio, tenta restaurar o que ja foi feito.
    Retorna (concluidos, erros) — concluidos: [(origem, destino)].
    """
    done: list[tuple[Path, Path]] = []
    errors: list[str] = []
    temps: list[tuple[Path, Path, Path]] = []  # (origem, temp, destino)
    for i, (src, dst) in enumerate(pairs):
        tmp = src.parent / f".takeid-{uuid.uuid4().hex[:10]}-{i}{src.suffix}"
        try:
            src.rename(tmp)
            temps.append((src, tmp, dst))
        except OSError as exc:
            errors.append(f"{src.name}: não foi possível renomear ({exc})")
            break
    if errors:
        for src, tmp, _dst in temps:
            try:
                tmp.rename(src)
            except OSError:
                errors.append(f"{src.name}: falha ao restaurar após erro")
        return done, errors
    for src, tmp, dst in temps:
        try:
            tmp.rename(dst)
            done.append((src, dst))
        except OSError as exc:
            errors.append(f"{src.name} -> {dst.name}: falhou ({exc})")
            break
    if errors:
        # Restaura os ja concluidos e os temporarios restantes.
        for src, dst in done:
            try:
                dst.rename(src)
            except OSError:
                errors.append(f"{src.name}: falha ao restaurar após erro")
        for src, tmp, dst in temps:
            if tmp.exists() and (src, dst) not in done:
                try:
                    tmp.rename(src)
                except OSError:
                    errors.append(f"{src.name}: falha ao restaurar após erro")
        return [], errors
    return done, errors


def apply_plan(plan, log_dir):
    """Aplica um plano ja validado. Retorna dict com o resultado.

    Levanta ValueError se houver qualquer conflito — o lote nao
    aplica pela metade por decisao do usuario: ou esta tudo certo,
    ou nada acontece.
    """
    if has_conflicts(plan):
        raise ValueError(
            f"Lote bloqueado: {count_conflicts(plan)} conflito(s). "
            "Resolva ou retire os arquivos da lista.")
    pairs = [(e.original_path, e.new_path) for e in plan
             if not e.no_change and e.new_path is not None]
    skipped = sum(1 for e in plan if e.no_change)
    done, errors = _rename_two_pass(pairs)
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    if done:
        save_last_log(log_dir, done)
        append_history(log_dir, done)
    return {
        "renomeados": len(done),
        "pulados": skipped,
        "erros": errors,
        "log_json": str(log_dir / "ultimo_lote.json"),
        "log_csv": str(log_dir / "ultimo_lote.csv"),
    }


# ---------------------------------------------------------------- log

def save_last_log(log_dir, done_pairs):
    """Grava ultimo_lote.json + .csv (de -> para)."""
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    rows = [{"de": str(src), "para": str(dst)} for src, dst in done_pairs]
    (log_dir / "ultimo_lote.json").write_text(
        json.dumps({"quando": datetime.now().isoformat(),
                    "total": len(rows), "arquivos": rows},
                   ensure_ascii=False, indent=2), encoding="utf-8")
    with open(log_dir / "ultimo_lote.csv", "w", newline="",
              encoding="utf-8") as fh:
        writer = csv.writer(fh)
        writer.writerow(["de", "para"])
        writer.writerows([(r["de"], r["para"]) for r in rows])
    return log_dir / "ultimo_lote.json"


def load_last_log(log_dir):
    """Retorna [(de Path, para Path)] do ultimo lote, ou []."""
    path = Path(log_dir) / "ultimo_lote.json"
    if not path.exists():
        return []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return [(Path(r["de"]), Path(r["para"]))
                for r in data.get("arquivos", [])]
    except (OSError, ValueError, KeyError):
        return []


def append_history(log_dir, done_pairs):
    """Acrescenta o lote ao historico (historico.json)."""
    log_dir = Path(log_dir)
    log_dir.mkdir(parents=True, exist_ok=True)
    path = log_dir / "historico.json"
    history = []
    if path.exists():
        try:
            history = json.loads(path.read_text(encoding="utf-8"))
        except ValueError:
            history = []
    history.append({
        "quando": datetime.now().isoformat(),
        "total": len(done_pairs),
        "arquivos": [{"de": str(s), "para": str(d)}
                     for s, d in done_pairs],
    })
    path.write_text(json.dumps(history, ensure_ascii=False, indent=2),
                    encoding="utf-8")
    return path


def load_history(log_dir):
    path = Path(log_dir) / "historico.json"
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except ValueError:
        return []


def undo_last_batch(log_dir):
    """Desfaz o ultimo lote: (para -> de), em duas passadas.

    Retorna {'restaurados': n, 'pulados': n, 'erros': [...]}.
    Se tudo foi restaurado, o log do ultimo lote e apagado (nao da
    para desfazer duas vezes o mesmo lote).
    """
    log_dir = Path(log_dir)
    entries = load_last_log(log_dir)
    if not entries:
        return {"restaurados": 0, "pulados": 0,
                "erros": ["Não há lote para desfazer."]}
    pairs, skipped, errors = [], 0, []
    existing = {str(d).lower() for _s, d in entries}
    for src, dst in entries:  # src=original, dst=nome novo
        if not dst.exists():
            skipped += 1
            errors.append(f"{dst.name}: arquivo renomeado não encontrado")
            continue
        if src.exists() and str(src).lower() not in existing:
            skipped += 1
            errors.append(f"{src.name}: o nome original já está ocupado")
            continue
        pairs.append((dst, src))
    done, rename_errors = _rename_two_pass(pairs)
    errors.extend(rename_errors)
    if done and not errors:
        for name in ("ultimo_lote.json", "ultimo_lote.csv"):
            try:
                (log_dir / name).unlink()
            except OSError:
                pass
    elif done:
        # Desfazer parcial: o log passa a cobrir so o que restou.
        remaining = [(s, d) for s, d in entries
                     if (d, s) not in done]
        save_last_log(log_dir, remaining)
    return {"restaurados": len(done), "pulados": skipped, "erros": errors}
