"""TakeID 1.0.0 by DX Labs — renomeacao em lote (Windows).

Tkinter, fundo escuro roxo como o mockup. Nada e renomeado sem
preview: a lista mostra Original -> Novo, conflitos em vermelho
bloqueiam o botao Renomear, e cada lote aplicado grava um log
de -> para (CSV + JSON) que o Desfazer restaura, mesmo apos
fechar e reabrir o app. So troca o nome, no mesmo lugar — nada
e movido, copiado ou apagado.
"""
import json
import os
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from rename_engine import (
    Settings, apply_plan, build_plan, count_conflicts,
    get_photo_datetime, has_conflicts, load_history,
    load_last_log, undo_last_batch,
)

VERSION = "1.0.0"
TITLE = f"TakeID {VERSION} by DX Labs"

BG = "#1B1030"
BG_PANEL = "#241640"
BG_LIST = "#2A1B4A"
FG = "#EDE9FE"
FG_MUTED = "#B8A8D8"
ACCENT = "#8B2CE8"
ACCENT_LIGHT = "#A855F7"
DANGER_BG = "#4A0E14"

# Presets que vem prontos (editaveis; salvos em takeid_dados/).
DEFAULT_PRESETS = [
    {"nome": "Padrão TakeID",
     "settings": {"pattern": "{evento}_{tipo}_{seq:0000}",
                  "evento": "EXPO2026", "cliente": "",
                  "tipo_foto": "FOTO", "tipo_video": "TAKE",
                  "inicio_fotos": 1, "inicio_videos": 1}},
    {"nome": "Casamento",
     "settings": {"pattern": "{datafoto}_{cliente}_{seq:03}",
                  "evento": "", "cliente": "Karoline-Manuel",
                  "tipo_foto": "FOTO", "tipo_video": "TAKE",
                  "inicio_fotos": 1, "inicio_videos": 1}},
    {"nome": "Ensaio",
     "settings": {"pattern": "{cliente}_{tipo}_{datafoto}_{seq:02}",
                  "evento": "", "cliente": "Mayara-Ewerton",
                  "tipo_foto": "FOTO", "tipo_video": "TAKE",
                  "inicio_fotos": 1, "inicio_videos": 1}},
    {"nome": "Evento corporativo",
     "settings": {"pattern": "{evento}_{datafoto}_{seq:03}",
                  "evento": "INDEX25", "cliente": "",
                  "tipo_foto": "FOTO", "tipo_video": "TAKE",
                  "inicio_fotos": 1, "inicio_videos": 1}},
    {"nome": "Feira / Estande",
     "settings": {"pattern": "{cliente}_{evento}_{seq:03}",
                  "evento": "WindPower2026", "cliente": "FairWind",
                  "tipo_foto": "FOTO", "tipo_video": "TAKE",
                  "inicio_fotos": 1, "inicio_videos": 1}},
    {"nome": "Só numerar",
     "settings": {"pattern": "{nome}_{seq:03}",
                  "evento": "", "cliente": "",
                  "tipo_foto": "FOTO", "tipo_video": "TAKE",
                  "inicio_fotos": 1, "inicio_videos": 1}},
]

FORMATOS_DATA = ["%Y-%m-%d", "%Y%m%d", "%d-%m-%Y"]


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).parent
    return Path(__file__).parent


def data_dir() -> Path:
    d = app_dir() / "takeid_dados"
    d.mkdir(parents=True, exist_ok=True)
    return d


class App:
    def __init__(self, root):
        self.root = root
        self.root.title(TITLE)
        self.root.geometry("1280x760")
        self.root.configure(bg=BG)
        self.data = data_dir()
        self.items = []          # [{path: Path, selected: bool}]
        self.plan = []           # [PlanEntry] do motor, na ordem da lista
        self.plan_by_path = {}
        self.thumbs = {}         # (str path, mtime, size) -> PhotoImage
        self.filter_type = tk.StringVar(value="Todos")
        self.search_var = tk.StringVar()
        self.sort_var = tk.StringVar(value="Nome")
        self.subpastas_var = tk.BooleanVar(value=False)

        # Variaveis do padrao (qualquer mudanca recalcula o preview).
        self.pattern_var = tk.StringVar(value="{evento}_{tipo}_{seq:0000}")
        self.evento_var = tk.StringVar(value="EXPO2026")
        self.cliente_var = tk.StringVar(value="")
        self.tipo_foto_var = tk.StringVar(value="FOTO")
        self.tipo_video_var = tk.StringVar(value="TAKE")
        self.inicio_fotos_var = tk.IntVar(value=1)
        self.inicio_videos_var = tk.IntVar(value=1)
        self.formato_data_var = tk.StringVar(value=FORMATOS_DATA[0])
        self.maiusculas_var = tk.BooleanVar(value=False)
        self.espacos_var = tk.BooleanVar(value=False)
        self.data_arquivo_var = tk.BooleanVar(value=True)
        self.parear_var = tk.BooleanVar(value=True)
        for var in (self.pattern_var, self.evento_var, self.cliente_var,
                    self.tipo_foto_var, self.tipo_video_var,
                    self.inicio_fotos_var, self.inicio_videos_var,
                    self.formato_data_var, self.maiusculas_var,
                    self.espacos_var, self.data_arquivo_var,
                    self.parear_var):
            var.trace_add("write", lambda *_: self.refresh())
        self.search_var.trace_add("write", lambda *_: self.refresh_tree())
        self.filter_type.trace_add("write", lambda *_: self.refresh_tree())
        self.sort_var.trace_add("write", lambda *_: self.sort_and_refresh())

        self._style()
        self._build_top()
        # Rodape ANTES do painel principal: os Spinbox da aba Padrão
        # disparam o recálculo do preview ao serem criados, e o
        # refresh() precisa do status_label/botões já existindo.
        self._build_footer()
        self._build_main()
        self._load_presets()
        self.refresh()

    # ---------------------------------------------------------------- UI

    def _style(self):
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TFrame", background=BG)
        style.configure("TLabel", background=BG, foreground=FG)
        style.configure("TLabelFrame", background=BG_PANEL,
                        foreground=FG)
        style.configure("TButton", background=ACCENT, foreground="white",
                        borderwidth=0, padding=6)
        style.map("TButton", background=[("active", ACCENT_LIGHT),
                                         ("disabled", "#4A3A6A")])
        style.configure("TEntry", fieldbackground=BG_LIST,
                        foreground=FG, insertcolor=FG)
        style.configure("TCombobox", fieldbackground=BG_LIST,
                        foreground=FG)
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", background=BG_PANEL,
                        foreground=FG, padding=(10, 6))
        style.map("TNotebook.Tab",
                  background=[("selected", ACCENT)])
        style.configure("Treeview", background=BG_LIST, foreground=FG,
                        fieldbackground=BG_LIST, rowheight=68,
                        borderwidth=0)
        style.configure("Treeview.Heading", background=BG_PANEL,
                        foreground=FG, borderwidth=0)
        style.map("Treeview",
                  background=[("selected", ACCENT)])

    def _build_top(self):
        top = ttk.Frame(self.root, padding=(10, 8, 10, 4))
        top.pack(fill="x")
        ttk.Button(top, text="+ Adicionar Arquivos",
                   command=self.add_files).pack(side="left", padx=2)
        ttk.Button(top, text="Adicionar Pasta",
                   command=self.add_folder).pack(side="left", padx=2)
        ttk.Button(top, text="Limpar",
                   command=self.clear_list).pack(side="left", padx=2)
        ttk.Checkbutton(top, text="Incluir subpastas",
                        variable=self.subpastas_var).pack(side="left",
                                                          padx=8)
        for label in ("Todos", "JPG", "RAW", "Vídeos"):
            ttk.Radiobutton(top, text=label, value=label,
                            variable=self.filter_type).pack(side="left")
        ttk.Label(top, text="Buscar:").pack(side="left", padx=(12, 2))
        ttk.Entry(top, textvariable=self.search_var, width=22).pack(
            side="left")
        ttk.Label(top, text="Ordenar:").pack(side="left", padx=(12, 2))
        ttk.Combobox(top, textvariable=self.sort_var, width=18,
                     values=["Nome", "Data da foto",
                             "Data de modificação", "Tamanho"],
                     state="readonly").pack(side="left")
        sel = ttk.Frame(self.root, padding=(10, 0, 10, 4))
        sel.pack(fill="x")
        ttk.Button(sel, text="Selecionar somente filtro",
                   command=self.select_only_filter).pack(side="left",
                                                         padx=2)
        ttk.Button(sel, text="Marcar visíveis",
                   command=lambda: self.toggle_visible(True)).pack(
                       side="left", padx=2)
        ttk.Button(sel, text="Desmarcar visíveis",
                   command=lambda: self.toggle_visible(False)).pack(
                       side="left", padx=2)
        ttk.Label(sel, text="Filtrar não é selecionar: um arquivo "
                  "escondido pelo filtro continua marcado.",
                  foreground=FG_MUTED).pack(side="left", padx=10)

    def _build_main(self):
        paned = ttk.PanedWindow(self.root, orient="horizontal")
        paned.pack(fill="both", expand=True, padx=10, pady=4)
        left = ttk.Frame(paned)
        paned.add(left, weight=3)
        cols = ("sel", "original", "novo", "tipo", "data", "status")
        self.tree = ttk.Treeview(left, columns=cols, show="tree headings",
                                 selectmode="browse")
        self.tree.column("#0", width=70, stretch=False)
        self.tree.heading("#0", text="")
        widths = {"sel": 36, "original": 210, "novo": 230, "tipo": 70,
                  "data": 110, "status": 170}
        for col in cols:
            self.tree.heading(col, text={
                "sel": "✓", "original": "Arquivo Original",
                "novo": "Novo Nome (Prévia)", "tipo": "Tipo",
                "data": "Data da foto",
                "status": "Status"}.get(col, col))
            self.tree.column(col, width=widths[col], stretch=True)
        self.tree.tag_configure("conflict", background=DANGER_BG,
                                foreground="#FFB3B3")
        self.tree.tag_configure("nochange", foreground=FG_MUTED)
        scroll = ttk.Scrollbar(left, orient="vertical",
                               command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.tree.bind("<Button-1>", self.on_tree_click)
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)

        right = ttk.Frame(paned)
        paned.add(right, weight=1)
        self.notebook = ttk.Notebook(right)
        self.notebook.pack(fill="both", expand=True)
        self._build_tab_padrao()
        self._build_tab_presets()
        self._build_tab_metadados()
        self._build_tab_historico()
        self._build_tab_sobre()

    def _build_tab_padrao(self):
        tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(tab, text="Padrão")
        ttk.Label(tab, text="Padrão de Renomeação").pack(anchor="w")
        ttk.Entry(tab, textvariable=self.pattern_var).pack(fill="x",
                                                           pady=4)
        ttk.Label(tab, text="Tokens: {evento} {tipo} {nome} {seq} "
                  "{seq:0000} {data} {datafoto} {hora} {cliente} "
                  "{ext} {pasta}", foreground=FG_MUTED,
                  wraplength=300).pack(anchor="w", pady=2)
        for label, var in (("Evento / prefixo:", self.evento_var),
                           ("Cliente:", self.cliente_var),
                           ("Tipo foto (JPG/RAW):", self.tipo_foto_var),
                           ("Tipo vídeo:", self.tipo_video_var)):
            ttk.Label(tab, text=label).pack(anchor="w", pady=(6, 0))
            ttk.Entry(tab, textvariable=var).pack(fill="x")
        row = ttk.Frame(tab)
        row.pack(fill="x", pady=(8, 0))
        ttk.Label(row, text="Início fotos:").pack(side="left")
        tk.Spinbox(row, from_=1, to=999999, width=7,
                   textvariable=self.inicio_fotos_var).pack(side="left",
                                                            padx=4)
        ttk.Label(row, text="Início vídeos:").pack(side="left")
        tk.Spinbox(row, from_=1, to=999999, width=7,
                   textvariable=self.inicio_videos_var).pack(side="left",
                                                             padx=4)
        ttk.Label(tab, text="Formato da data:").pack(anchor="w",
                                                      pady=(8, 0))
        ttk.Combobox(tab, textvariable=self.formato_data_var,
                     values=FORMATOS_DATA, state="readonly").pack(
                         fill="x")
        for text, var in (("Manter extensão do arquivo", None),
                          ("Usar data do arquivo (quando aplicável)",
                           self.data_arquivo_var),
                          ("Padronizar para MAIÚSCULAS",
                           self.maiusculas_var),
                          ("Substituir espaços por _", self.espacos_var),
                          ("Parear JPG + RAW com o mesmo número",
                           self.parear_var)):
            if var is None:
                ttk.Label(tab, text="✓ " + text,
                          foreground=FG_MUTED).pack(anchor="w", pady=2)
            else:
                ttk.Checkbutton(tab, text=text, variable=var).pack(
                    anchor="w", pady=2)
        ttk.Label(tab, text="A extensão original é sempre mantida, "
                  "com a mesma caixa (.jpg fica .jpg).",
                  foreground=FG_MUTED, wraplength=300).pack(anchor="w",
                                                           pady=6)

    def _build_tab_presets(self):
        tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(tab, text="Presets")
        ttk.Label(tab, text="Presets salvos (ficam neste PC, "
                  "sem conta e sem nuvem):").pack(anchor="w")
        self.preset_list = tk.Listbox(tab, bg=BG_LIST, fg=FG,
                                      selectmode="browse", height=8)
        self.preset_list.pack(fill="both", expand=True, pady=6)
        ttk.Button(tab, text="Aplicar preset",
                   command=self.apply_preset).pack(fill="x", pady=2)
        ttk.Button(tab, text="Salvar padrão atual como preset",
                   command=self.save_preset).pack(fill="x", pady=2)
        ttk.Button(tab, text="Excluir preset",
                   command=self.delete_preset).pack(fill="x", pady=2)

    def _build_tab_metadados(self):
        tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(tab, text="Metadados (EXIF)")
        self.meta_text = tk.Text(tab, bg=BG_LIST, fg=FG, height=20,
                                 wrap="word", state="disabled")
        self.meta_text.pack(fill="both", expand=True)
        self._set_meta("Selecione um arquivo na lista para ver "
                       "a data EXIF, o tamanho e as dimensões.")

    def _build_tab_historico(self):
        tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(tab, text="Histórico")
        self.history_list = tk.Listbox(tab, bg=BG_LIST, fg=FG,
                                       selectmode="browse", height=8)
        self.history_list.pack(fill="both", expand=True, pady=4)
        self.history_list.bind("<<ListboxSelect>>",
                               self.on_history_select)
        self.history_text = tk.Text(tab, bg=BG_LIST, fg=FG, height=12,
                                    wrap="word", state="disabled")
        self.history_text.pack(fill="both", expand=True)

    def _build_tab_sobre(self):
        tab = ttk.Frame(self.notebook, padding=10)
        self.notebook.add(tab, text="Sobre")
        ttk.Label(tab, text=f"TakeID {VERSION} by DX Labs",
                  font=("", 12, "bold")).pack(anchor="w")
        ttk.Label(tab, wraplength=300, justify="left", text=
            "Renomeação em lote para fotos, RAW e vídeos. "
            "Padrão: {evento}_{tipo}_{seq:0000} — ex.: "
            "EXPO2026_FOTO_0001.JPG e EXPO2026_TAKE_0001.MP4. "
            "JPG e RAW do mesmo clique ganham o mesmo número. "
            "Conflitos bloqueiam o lote. Desfazer restaura o "
            "último lote pelo log de/para.\n\n"
            "O que NÃO faz: não move, copia ou apaga arquivos; "
            "não converte formato; não renomeia pastas; não "
            "usa nuvem, conta ou IA. Tudo roda local, offline.\n\n"
            "Teste primeiro numa pasta-cópia pequena (20–50 "
            "arquivos), nunca direto na pasta original.").pack(
                anchor="w", pady=8)

    def _build_footer(self):
        footer = ttk.Frame(self.root, padding=(10, 4, 10, 10))
        footer.pack(side="bottom", fill="x")
        self.status_label = ttk.Label(footer, text="Nenhum arquivo")
        self.status_label.pack(side="left")
        self.undo_button = ttk.Button(footer, text="Desfazer último lote",
                                      command=self.do_undo)
        self.undo_button.pack(side="right", padx=4)
        self.rename_button = ttk.Button(footer, text="Renomear Arquivos",
                                        command=self.do_rename)
        self.rename_button.pack(side="right", padx=4)

    # ---------------------------------------------------------------- dados

    def _set_meta(self, text):
        self.meta_text.configure(state="normal")
        self.meta_text.delete("1.0", "end")
        self.meta_text.insert("1.0", text)
        self.meta_text.configure(state="disabled")

    def _load_presets(self):
        self.presets_path = self.data / "presets.json"
        if self.presets_path.exists():
            try:
                self.presets = json.loads(
                    self.presets_path.read_text(encoding="utf-8"))
            except ValueError:
                self.presets = list(DEFAULT_PRESETS)
        else:
            self.presets = list(DEFAULT_PRESETS)
            self._save_presets()
        self.preset_list.delete(0, "end")
        for preset in self.presets:
            self.preset_list.insert("end", preset["nome"])

    def _save_presets(self):
        self.presets_path.write_text(
            json.dumps(self.presets, ensure_ascii=False, indent=2),
            encoding="utf-8")

    def get_settings(self) -> Settings:
        try:
            inicio_fotos = int(self.inicio_fotos_var.get())
        except (tk.TclError, ValueError):
            inicio_fotos = 1
        try:
            inicio_videos = int(self.inicio_videos_var.get())
        except (tk.TclError, ValueError):
            inicio_videos = 1
        return Settings(
            pattern=self.pattern_var.get(),
            evento=self.evento_var.get(),
            cliente=self.cliente_var.get(),
            tipo_foto=self.tipo_foto_var.get() or "FOTO",
            tipo_video=self.tipo_video_var.get() or "TAKE",
            inicio_fotos=max(1, inicio_fotos),
            inicio_videos=max(1, inicio_videos),
            formato_data=self.formato_data_var.get() or "%Y-%m-%d",
            maiusculas=self.maiusculas_var.get(),
            substituir_espacos=self.espacos_var.get(),
            usar_data_arquivo=self.data_arquivo_var.get(),
            parear_raw_jpg=self.parear_var.get(),
        )

    def apply_settings(self, settings: dict):
        self.pattern_var.set(settings.get("pattern", ""))
        self.evento_var.set(settings.get("evento", ""))
        self.cliente_var.set(settings.get("cliente", ""))
        self.tipo_foto_var.set(settings.get("tipo_foto", "FOTO"))
        self.tipo_video_var.set(settings.get("tipo_video", "TAKE"))
        self.inicio_fotos_var.set(settings.get("inicio_fotos", 1))
        self.inicio_videos_var.set(settings.get("inicio_videos", 1))
        self.refresh()

    # ------------------------------------------------------------- lista

    def add_files(self):
        chosen = filedialog.askopenfilenames(
            title="Adicionar arquivos",
            filetypes=[("Fotos e vídeos", "*.jpg *.jpeg *.arw *.cr2 "
                        "*.cr3 *.nef *.dng *.raf *.rw2 *.orf *.mp4 "
                        "*.mov *.mkv *.avi *.mts *.m2ts *.m4v *.webm "
                        "*.*"),
                       ("Todos os arquivos", "*.*")])
        self._add_paths([Path(p) for p in chosen])

    def add_folder(self):
        folder = filedialog.askdirectory(title="Adicionar pasta")
        if not folder:
            return
        root = Path(folder)
        if self.subpastas_var.get():
            paths = [p for p in sorted(root.rglob("*")) if p.is_file()]
        else:
            paths = [p for p in sorted(root.iterdir()) if p.is_file()]
        self._add_paths(paths)

    def _add_paths(self, paths):
        known = {str(it["path"]) for it in self.items}
        added = 0
        for path in paths:
            if str(path) not in known:
                self.items.append({"path": path, "selected": True})
                known.add(str(path))
                added += 1
        if added:
            self.sort_items()
            self.refresh()
        elif paths:
            messagebox.showinfo("TakeID", "Os arquivos escolhidos já "
                                "estão na lista.")

    def clear_list(self):
        # So a lista: nenhum arquivo e apagado do disco.
        self.items = []
        self.refresh()

    def sort_items(self):
        mode = self.sort_var.get()
        if mode == "Nome":
            key = lambda it: (str(it["path"].parent).lower(),
                              it["path"].name.lower())
        elif mode == "Data da foto":
            key = lambda it: (get_photo_datetime(it["path"])[0]
                              or __import__("datetime").datetime.min)
        elif mode == "Data de modificação":
            key = lambda it: it["path"].stat().st_mtime \
                if it["path"].exists() else 0
        else:  # Tamanho
            key = lambda it: it["path"].stat().st_size \
                if it["path"].exists() else 0
        self.items.sort(key=key)

    def sort_and_refresh(self):
        self.sort_items()
        self.refresh()

    def visible_items(self):
        ftype = self.filter_type.get()
        needle = self.search_var.get().strip().lower()
        out = []
        for it in self.items:
            kind = self._kind(it["path"])
            if ftype == "JPG" and kind != "JPG":
                continue
            if ftype == "RAW" and kind != "RAW":
                continue
            if ftype == "Vídeos" and kind != "VIDEO":
                continue
            if needle and needle not in it["path"].name.lower():
                continue
            out.append(it)
        return out

    @staticmethod
    def _kind(path):
        from rename_engine import classify
        return classify(path)

    def select_only_filter(self):
        visible = {str(it["path"]) for it in self.visible_items()}
        for it in self.items:
            it["selected"] = str(it["path"]) in visible
        self.refresh()

    def toggle_visible(self, value):
        visible = {str(it["path"]) for it in self.visible_items()}
        for it in self.items:
            if str(it["path"]) in visible:
                it["selected"] = value
        self.refresh()

    # ----------------------------------------------------------- preview

    def refresh(self):
        selected = [it["path"] for it in self.items if it["selected"]]
        try:
            self.plan = build_plan(selected, self.get_settings())
        except Exception as exc:  # nunca travar a tela por um padrao
            self.plan = []
            if hasattr(self, "status_label"):
                self.status_label.configure(
                    text=f"Erro no padrão: {exc}")
                self.rename_button.configure(state="disabled")
            self.refresh_tree()
            return
        self.plan_by_path = {str(e.original_path): e for e in self.plan}
        self.refresh_tree()
        self.refresh_history()
        if not hasattr(self, "status_label"):
            return  # ainda construindo a janela (trace de um widget)
        total = len(self.items)
        sel = len(selected)
        conflicts = count_conflicts(self.plan)
        status = f"{total} arquivo(s) · {sel} selecionado(s)"
        if conflicts:
            status += f" · {conflicts} com conflito — resolva para liberar"
        elif sel:
            status += " · Novo nome válido para todos os arquivos"
        self.status_label.configure(text=status)
        self.rename_button.configure(
            state="normal" if sel and not has_conflicts(self.plan)
            else "disabled")
        self.undo_button.configure(
            state="normal" if load_last_log(self.data) else "disabled")

    def refresh_tree(self):
        if not hasattr(self, "tree"):
            return
        for row in self.tree.get_children():
            self.tree.delete(row)
        for it in self.visible_items():
            path = it["path"]
            entry = self.plan_by_path.get(str(path))
            if entry is None:
                novo, status, tags = "Não selecionado", "", ()
                data_txt = ""
            elif entry.error:
                novo, status, tags = entry.new_name or "—", entry.error, \
                    ("conflict",)
            elif entry.no_change:
                novo, status, tags = entry.new_name, "Sem alteração", \
                    ("nochange",)
            else:
                novo, status, tags = entry.new_name, "OK", ()
            if entry is not None and entry.photo_datetime:
                data_txt = entry.photo_datetime.strftime("%d/%m/%Y")
                if not entry.has_exif:
                    data_txt += " (sem EXIF)"
            else:
                data_txt = ""
            thumb = self._thumb(path)
            self.tree.insert("", "end", iid=str(path),
                             image=thumb if thumb else "",
                             values=("☑" if it["selected"] else "☐",
                                     path.name, novo, entry.tipo
                                     if entry else self._kind(path),
                                     data_txt, status),
                             tags=tags)

    def _thumb(self, path):
        if path.suffix.lower() not in (".jpg", ".jpeg"):
            return None
        try:
            stat = path.stat()
            key = (str(path), stat.st_mtime, stat.st_size)
            if key in self.thumbs:
                return self.thumbs[key]
            from PIL import Image, ImageTk
            with Image.open(path) as img:
                img.thumbnail((64, 64))
                photo = ImageTk.PhotoImage(img.copy())
            # Limita o cache para nao crescer sem fim em lotes grandes.
            if len(self.thumbs) > 400:
                self.thumbs.clear()
            self.thumbs[key] = photo
            return photo
        except Exception:
            return None

    def on_tree_click(self, event):
        row = self.tree.identify_row(event.y)
        col = self.tree.identify_column(event.x)
        if not row or col != "#1":
            return
        for it in self.items:
            if str(it["path"]) == row:
                it["selected"] = not it["selected"]
                break
        self.refresh()

    def on_tree_select(self, _event):
        selected = self.tree.selection()
        if not selected:
            return
        path = Path(selected[0])
        entry = self.plan_by_path.get(str(path))
        try:
            stat = path.stat()
            size_mb = stat.st_size / (1024 * 1024)
        except OSError:
            size_mb = 0
        dt, has_exif = get_photo_datetime(path)
        dims = ""
        try:
            from PIL import Image
            with Image.open(path) as img:
                dims = f"{img.width} × {img.height} px"
        except Exception:
            pass
        lines = [
            f"Arquivo: {path.name}",
            f"Pasta: {path.parent}",
            f"Tipo: {self._kind(path)}"
            + (f" ({entry.tipo})" if entry else ""),
            f"Data da foto: "
            f"{dt.strftime('%d/%m/%Y %H:%M:%S') if dt else '—'}"
            + ("" if has_exif else "  — sem EXIF (data de modificação)"),
            f"Data de modificação: "
            f"{__import__('datetime').datetime.fromtimestamp(stat.st_mtime).strftime('%d/%m/%Y %H:%M:%S') if stat else '—'}",
            f"Tamanho: {size_mb:.2f} MB",
            f"Dimensões: {dims or '—'}",
            f"Novo nome: {entry.new_name if entry else '—'}",
        ]
        self._set_meta("\n".join(lines))

    # ---------------------------------------------------------- presets

    def apply_preset(self):
        sel = self.preset_list.curselection()
        if not sel:
            messagebox.showinfo("TakeID", "Escolha um preset na lista.")
            return
        preset = self.presets[sel[0]]
        self.apply_settings(preset["settings"])
        messagebox.showinfo("TakeID",
                            f"Preset “{preset['nome']}” aplicado.")

    def save_preset(self):
        from tkinter import simpledialog
        name = simpledialog.askstring(
            "Salvar preset", "Nome do preset:")
        if not name:
            return
        settings = self.get_settings().to_dict()
        self.presets = [p for p in self.presets if p["nome"] != name]
        self.presets.append({"nome": name, "settings": settings})
        self._save_presets()
        self._load_presets()

    def delete_preset(self):
        sel = self.preset_list.curselection()
        if not sel:
            return
        name = self.presets[sel[0]]["nome"]
        if not messagebox.askyesno("TakeID",
                                   f"Excluir o preset “{name}”?"):
            return
        del self.presets[sel[0]]
        self._save_presets()
        self._load_presets()

    # --------------------------------------------------------- historico

    def refresh_history(self):
        if not hasattr(self, "history_list"):
            return
        history = load_history(self.data)
        current = self.history_list.get(0, "end")
        labels = [f"{h.get('quando', '')[:19].replace('T', ' ')} — "
                  f"{h.get('total', 0)} arquivo(s)" for h in history]
        if list(current) != labels:
            self.history_list.delete(0, "end")
            for label in labels:
                self.history_list.insert("end", label)

    def on_history_select(self, _event):
        sel = self.history_list.curselection()
        if not sel:
            return
        history = load_history(self.data)
        batch = history[sel[0]]
        lines = [f"{r['de']}  ->  {r['para']}"
                 for r in batch.get("arquivos", [])]
        text = self.history_text
        text.configure(state="normal")
        text.delete("1.0", "end")
        text.insert("1.0", "\n".join(lines) or "Sem arquivos.")
        text.configure(state="disabled")

    # -------------------------------------------------- renomear / desfazer

    def do_rename(self):
        selected = [e for e in self.plan if not e.no_change]
        if not selected:
            messagebox.showinfo("TakeID", "Nada para renomear: os "
                                "arquivos selecionados já têm o nome "
                                "proposto.")
            return
        if has_conflicts(self.plan):
            messagebox.showwarning(
                "TakeID", "Há conflitos na lista. Resolva ou retire "
                "os arquivos com conflito antes de renomear.")
            return
        exemplo = (f"{selected[0].original_name}  ->  "
                   f"{selected[0].new_name}")
        if not messagebox.askyesno(
                "Confirmar renomeação",
                f"Renomear {len(selected)} arquivo(s)?\n\n{exemplo}\n"
                "Os nomes são trocados na própria pasta. "
                "Nada é movido, copiado ou apagado."):
            return
        try:
            result = apply_plan(self.plan, self.data)
        except ValueError as exc:
            messagebox.showerror("TakeID", str(exc))
            return
        if result["erros"]:
            messagebox.showwarning(
                "TakeID",
                "O lote não foi aplicado e os arquivos foram "
                "restaurados.\n\n" + "\n".join(result["erros"]))
            self.refresh()
            return
        # Atualiza a lista: renomeados ganham o nome novo e saem
        # da selecao; os demais continuam como estavam.
        new_by_old = {}
        for entry in self.plan:
            if not entry.no_change and entry.new_path is not None:
                new_by_old[str(entry.original_path)] = entry.new_path
        for it in self.items:
            if str(it["path"]) in new_by_old:
                it["path"] = new_by_old[str(it["path"])]
                it["selected"] = False
        msg = (f"{result['renomeados']} renomeado(s)")
        if result["pulados"]:
            msg += f" · {result['pulados']} já estava(m) com o nome certo"
        msg += (f"\n\nLog de/para salvo em:\n{result['log_csv']}\n"
                "Use “Desfazer último lote” para restaurar os nomes.")
        messagebox.showinfo("TakeID — lote aplicado", msg)
        self.refresh()

    def do_undo(self):
        if not load_last_log(self.data):
            messagebox.showinfo("TakeID", "Não há lote para desfazer.")
            return
        if not messagebox.askyesno(
                "Desfazer último lote",
                "Restaurar os nomes originais do último lote aplicado?"):
            return
        result = undo_last_batch(self.data)
        if result["erros"]:
            messagebox.showwarning(
                "TakeID — desfazer parcial",
                f"{result['restaurados']} restaurado(s), "
                f"{result['pulados']} pulado(s).\n\n"
                + "\n".join(result["erros"]))
        else:
            messagebox.showinfo(
                "TakeID", f"{result['restaurados']} arquivo(s) "
                "restaurado(s) com os nomes originais.")
        self.refresh()


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
