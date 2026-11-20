"""DX Rename 1.0.0 by DX Labs — renomeacao em lote (Windows).

Tkinter, visual do mockup: janela escura azul-marinho, sidebar com
a navegacao, tabela CLARA com miniaturas e painel direito escuro.
Nada e renomeado sem preview: a lista mostra Original -> Novo,
conflitos em vermelho bloqueiam o botao Renomear, e cada lote
aplicado grava um log de -> para (CSV + JSON) que o Desfazer
restaura, mesmo apos fechar e reabrir o app. So troca o nome, no
mesmo lugar — nada e movido, copiado ou apagado.

Navegacao (uma so, pela sidebar; a tabela fica sempre visivel e o
painel direito troca de conteudo):
  Renomear        -> Padrão (estrutura, tokens, numeração, interruptores)
  Presets         -> Presets salvos
  Metadados (EXIF)-> dados do arquivo selecionado
  Regras Avançadas-> parear JPG+RAW, tipos, início dos vídeos, formato da data
  Histórico       -> lotes aplicados (com estado vazio quando não há nenhum)
  Configurações   -> início, dígitos, formato da data, tipos, pasta de dados
  Sobre           -> sobre o app
"""
import json
import os
import re
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
TITLE = f"DX Rename {VERSION} by DX Labs"

# Cores do mockup.
BG = "#15102B"            # fundo da janela
BG_PANEL = "#241A45"      # painéis escuros
BG_LIST = "#2A1B4A"       # campos escuros
SIDEBAR = "#1E1438"       # sidebar (um tom acima do fundo)
FG = "#FFFFFF"
FG_MUTED = "#B8AED6"
ACCENT = "#8B2CE8"
ACCENT_LIGHT = "#A855F7"
DANGER_BG = "#4A0E14"
LIGHT_BG = "#F2EFFA"      # tabela clara
LIGHT_FG = "#1A1033"

# Presets que vem prontos (editaveis; salvos em dxrename_dados/).
DEFAULT_PRESETS = [
    {"nome": "Padrão DX Rename",
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


def assets_dir() -> Path:
    """Pasta de imagens: dentro do .exe empacotado (PyInstaller
    --add-data, _MEIPASS) ou, rodando do fonte, windows/assets/."""
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        return Path(meipass) / "assets"
    return app_dir() / "assets"


def data_dir() -> Path:
    d = app_dir() / "dxrename_dados"
    # Migração da v1.0.0 (o app se chamava TakeID): se a pasta
    # antiga existir e a nova não, aproveita presets e histórico.
    old = app_dir() / "takeid_dados"
    if old.exists() and not d.exists():
        try:
            old.rename(d)
        except OSError:
            pass
    d.mkdir(parents=True, exist_ok=True)
    return d


def _enable_dark_titlebar(root):
    """Barra de titulo escura no Windows 10/11 (DWM).

    No Linux / Windows antigo nao faz nada (a barra segue o tema
    do sistema) — o cabecalho escuro dentro da janela existe de
    qualquer forma. Nunca pode quebrar a abertura do app.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes
        hwnd = ctypes.windll.user32.GetParent(root.winfo_id())
        value = ctypes.c_int(1)
        ctypes.windll.dwmapi.DwmSetWindowAttribute(
            hwnd, 20, ctypes.byref(value), ctypes.sizeof(value))
    except Exception:
        pass


class Toggle(tk.Frame):
    """Interruptor estilo mockup: pilula roxa (ligado) / cinza (desligado).

    Desenhado num Canvas porque o ttk.Checkbutton do Tkinter nao tem
    visual de interruptor. O estado vive num BooleanVar, como um
    Checkbutton comum — o resto do app nao precisa saber a diferenca.
    """

    def __init__(self, parent, variable, text="", state="normal"):
        super().__init__(parent, bg=BG_PANEL)
        self.variable = variable
        self._state = state
        self.canvas = tk.Canvas(
            self, width=46, height=26, bg=BG_PANEL,
            highlightthickness=0,
            cursor="hand2" if state == "normal" else "arrow")
        self.canvas.pack(side="left")
        if text:
            tk.Label(self, text=text, bg=BG_PANEL, fg=FG,
                     font=("", 10)).pack(side="left", padx=(8, 0))
        self.canvas.bind("<Button-1>", self._on_click)
        variable.trace_add("write", lambda *_: self._draw())
        self._draw()

    def _on_click(self, _event=None):
        if self._state != "normal":
            return
        self.variable.set(not self.variable.get())

    def _draw(self):
        on = bool(self.variable.get())
        self.canvas.delete("all")
        if self._state != "normal":
            color = "#5B4A86" if on else "#3A3350"
        else:
            color = ACCENT if on else "#5A5470"
        self.canvas.create_oval(2, 2, 24, 24, fill=color, outline=color)
        self.canvas.create_oval(22, 2, 44, 24, fill=color, outline=color)
        self.canvas.create_rectangle(13, 2, 33, 24, fill=color,
                                     outline=color)
        x = 32 if on else 12
        self.canvas.create_oval(x - 9, 4, x + 9, 22, fill="white",
                                outline="white")


class App:
    def __init__(self, root):
        self.root = root
        self.root.title(TITLE)
        self.root.geometry("1360x820")
        self.root.minsize(1120, 640)
        self.root.configure(bg=BG)
        _enable_dark_titlebar(root)
        try:
            icon = app_dir() / "assets" / "icon.png"
            if icon.exists():
                from PIL import Image, ImageTk
                self._icon_photo = ImageTk.PhotoImage(
                    Image.open(icon).resize((32, 32)))
                root.iconphoto(False, self._icon_photo)
        except Exception:
            pass
        self.data = data_dir()
        self.items = []          # [{path: Path, selected: bool}]
        self.plan = []           # [PlanEntry] do motor, na ordem da lista
        self.plan_by_path = {}
        self.thumbs = {}         # (str path, mtime, size) -> PhotoImage
        self.filter_type = tk.StringVar(value="Todos")
        self.search_var = tk.StringVar()
        self.sort_var = tk.StringVar(value="Nome")
        self.subpastas_var = tk.BooleanVar(value=False)
        self.current_view = "renomear"
        self._pending_view = "renomear"

        # Variaveis do padrao (qualquer mudanca recalcula o preview).
        self.pattern_var = tk.StringVar(value="{evento}_{tipo}_{seq:0000}")
        self.evento_var = tk.StringVar(value="EXPO2026")
        self.cliente_var = tk.StringVar(value="")
        self.tipo_foto_var = tk.StringVar(value="FOTO")
        self.tipo_video_var = tk.StringVar(value="TAKE")
        self.inicio_fotos_var = tk.IntVar(value=1)
        self.inicio_videos_var = tk.IntVar(value=1)
        self.digits_var = tk.IntVar(value=4)
        self.numeracao_var = tk.StringVar(value="Crescente")
        self.padrao_combo_var = tk.StringVar(value="Personalizado")
        self.manter_extensao_var = tk.BooleanVar(value=True)
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
        self.digits_var.trace_add("write", lambda *_: self._apply_digits())
        self.search_var.trace_add("write", lambda *_: self.refresh_tree())
        self.filter_type.trace_add("write", lambda *_: self.refresh_tree())
        self.sort_var.trace_add("write", lambda *_: self.sort_and_refresh())

        self._style()
        self._build_shell()
        # Rodape ANTES do conteudo: os Spinbox disparam o recalculo
        # do preview ao serem criados, e o refresh() precisa do
        # status_label/botoes ja existindo.
        self._build_footer()
        self._build_header()
        self._build_content()
        self._load_presets()
        self._show_view(self._pending_view)
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
        style.configure("TButton", background=ACCENT, foreground="white",
                        borderwidth=0, padding=6)
        style.map("TButton", background=[("active", ACCENT_LIGHT),
                                         ("disabled", "#4A3A6A")])
        # Botao roxo (acao principal) e botao escuro (acao secundaria).
        style.configure("Accent.TButton", background=ACCENT,
                        foreground="white", borderwidth=0,
                        padding=(14, 8), font=("", 11, "bold"))
        style.map("Accent.TButton",
                  background=[("active", ACCENT_LIGHT),
                              ("disabled", "#4A3A6A")],
                  foreground=[("disabled", FG_MUTED)])
        style.configure("Big.Accent.TButton", background=ACCENT,
                        foreground="white", borderwidth=0,
                        padding=(20, 11), font=("", 12, "bold"))
        style.map("Big.Accent.TButton",
                  background=[("active", ACCENT_LIGHT),
                              ("disabled", "#4A3A6A")],
                  foreground=[("disabled", FG_MUTED)])
        style.configure("Dark.TButton", background="#3A2A63",
                        foreground="white", borderwidth=0,
                        padding=(12, 8), font=("", 11))
        style.map("Dark.TButton",
                  background=[("active", "#4A3A7A"),
                              ("disabled", "#2A2145")],
                  foreground=[("disabled", FG_MUTED)])
        # Campos escuros com texto branco sempre visivel.
        style.configure("Dark.TEntry", fieldbackground=BG_LIST,
                        foreground=FG, insertcolor=FG, borderwidth=0)
        style.configure("Dark.TCombobox", fieldbackground=BG_LIST,
                        background=BG_LIST, foreground=FG,
                        arrowcolor="white", borderwidth=0)
        style.map("Dark.TCombobox",
                  fieldbackground=[("readonly", BG_LIST)],
                  foreground=[("readonly", FG)],
                  background=[("readonly", BG_LIST)])
        # Tabela CLARA do mockup.
        style.configure("Light.Treeview", background=LIGHT_BG,
                        foreground=LIGHT_FG, fieldbackground=LIGHT_BG,
                        rowheight=48, borderwidth=0, font=("", 9))
        style.configure("Light.Treeview.Heading", background="#241A45",
                        foreground="white", borderwidth=0,
                        font=("", 10, "bold"))
        style.map("Light.Treeview",
                  background=[("selected", "#C9B8F5")],
                  foreground=[("selected", LIGHT_FG)])

    # ------------------------------------------------------------ shell

    def _build_shell(self):
        """Sidebar (esquerda) + area principal (direita)."""
        sidebar = tk.Frame(self.root, bg=SIDEBAR, width=232)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        self.sidebar = sidebar
        # Topo da sidebar: logo do DX Rename centralizada no espaco
        # acima do menu; o botao Renomear alinha com a linha de
        # filtros (Todos/JPG/RAW/Videos) da area principal (y=93).
        head = tk.Frame(sidebar, bg=SIDEBAR)
        head.pack(fill="x", padx=10, pady=(32, 6))
        self._sidebar_logo(head)
        # Menu vertical: um so sistema de navegacao.
        nav = tk.Frame(sidebar, bg=SIDEBAR)
        nav.pack(fill="x", pady=(16, 10))
        self.nav_buttons = {}
        items = [
            ("renomear", "⇄  Renomear"),
            ("presets", "▤  Presets"),
            ("metadados", "◉  Metadados (EXIF)"),
            ("regras", "{ }  Regras Avançadas"),
            ("historico", "↺  Histórico"),
            ("config", "⚙  Configurações"),
            ("sobre", "ⓘ  Sobre"),
        ]
        for key, label in items:
            btn = tk.Button(nav, text=label, bg=SIDEBAR, fg=FG,
                            activebackground=ACCENT,
                            activeforeground="white", relief="flat",
                            anchor="w", font=("", 11), padx=16, pady=10,
                            command=lambda k=key: self._show_view(k))
            btn.pack(fill="x", padx=8, pady=2)
            self.nav_buttons[key] = btn
        self._sidebar_footer(sidebar)
        self.main = tk.Frame(self.root, bg=BG)
        self.main.pack(side="right", fill="both", expand=True)

    def _sidebar_footer(self, sidebar):
        """Rodape da sidebar: logo da DX Labs (assets/dx_labs_logo.png,
        fundo transparente) no lugar do texto 'DX Labs'."""
        try:
            from PIL import Image, ImageTk
            import base64
            import io
            from dx_labs_logo_b64 import DATA
            img = Image.open(io.BytesIO(base64.b64decode("".join(DATA))))
            w = 160
            img = img.resize((w, int(w * img.height / img.width)),
                             Image.LANCZOS)
            self._footer_logo = ImageTk.PhotoImage(img)
            tk.Label(sidebar, image=self._footer_logo,
                     bg=SIDEBAR).pack(side="bottom", pady=(0, 30))
            return
        except Exception:
            pass
        tk.Label(sidebar, text="DX Labs", bg=SIDEBAR, fg=FG,
                 font=("", 13, "bold")).pack(side="bottom", pady=16)

    def _sidebar_logo(self, parent):
        """Topo da sidebar: logo do DX Rename (lockup horizontal,
        embutida em base64); se falhar, volta o titulo em texto."""
        try:
            from PIL import Image, ImageTk
            import base64
            import io
            from dx_rename_logo_b64 import DATA
            img = Image.open(io.BytesIO(base64.b64decode("".join(DATA))))
            w = 200
            img = img.resize((w, int(w * img.height / img.width)),
                             Image.LANCZOS)
            self._header_logo = ImageTk.PhotoImage(img)
            tk.Label(parent, image=self._header_logo,
                     bg=SIDEBAR).pack()
            return
        except Exception:
            pass
        tk.Label(parent, text="DX Rename", bg=SIDEBAR, fg=FG,
                 font=("", 15, "bold")).pack(anchor="w")
        tk.Label(parent, text="by DX Labs", bg=SIDEBAR, fg=FG_MUTED,
                 font=("", 10)).pack(anchor="w")
        canvas.create_polygon([(12, 42), (22, 30), (30, 38), (36, 32),
                               (40, 42)], fill="#E9D5FF")

    def _show_view(self, name):
        """Troca o painel direito; a tabela fica sempre visivel."""
        self.current_view = name
        if not hasattr(self, "panels"):
            self._pending_view = name
            return
        for key, frame in self.panels.items():
            frame.pack_forget()
        self.panels[name].pack(fill="both", expand=True)
        for key, btn in self.nav_buttons.items():
            btn.configure(bg=ACCENT if key == name else SIDEBAR)
        if name == "historico":
            self.refresh_history()

    # ----------------------------------------------------------- cabecalho

    def _build_header(self):
        header = tk.Frame(self.main, bg=BG)
        header.pack(fill="x", padx=16, pady=(14, 4))
        titles = tk.Frame(header, bg=BG)
        titles.pack(side="left")
        tk.Label(titles, text="Renomeação em Lote", bg=BG, fg=FG,
                 font=("", 20, "bold")).pack(anchor="w")
        tk.Label(titles,
                 text="Organize e padronize seus arquivos de forma "
                      "rápida e inteligente.",
                 bg=BG, fg=FG_MUTED, font=("", 11)).pack(anchor="w")
        actions = tk.Frame(header, bg=BG)
        actions.pack(side="right")
        ttk.Button(actions, text="+ Adicionar Arquivos",
                   style="Accent.TButton",
                   command=self.add_files).pack(side="left", padx=3)
        ttk.Button(actions, text="Adicionar Pasta",
                   style="Dark.TButton",
                   command=self.add_folder).pack(side="left", padx=3)
        ttk.Button(actions, text="Limpar", style="Dark.TButton",
                   command=self.clear_list).pack(side="left", padx=3)

        filters = tk.Frame(self.main, bg=BG)
        filters.pack(fill="x", padx=16, pady=6)
        row1 = tk.Frame(filters, bg=BG)
        row1.pack(fill="x")
        # Filtros como botoes-pilula (o selecionado fica roxo).
        self.filter_pills = {}
        for label in ("Todos", "JPG", "RAW", "Vídeos"):
            btn = tk.Button(row1, text=label, bg=BG_LIST, fg=FG,
                            activebackground=ACCENT,
                            activeforeground="white", relief="flat",
                            font=("", 10), padx=12, pady=4,
                            command=lambda v=label: self.filter_type.set(v))
            btn.pack(side="left", padx=2)
            self.filter_pills[label] = btn
        tk.Checkbutton(row1, text="Incluir subpastas",
                       variable=self.subpastas_var, bg=BG, fg=FG,
                       selectcolor=ACCENT, activebackground=BG,
                       activeforeground=FG, font=("", 10),
                       highlightthickness=0).pack(
                           side="left", padx=10)
        tk.Label(row1, text="Buscar:", bg=BG, fg=FG_MUTED,
                 font=("", 10)).pack(side="left", padx=(12, 4))
        ttk.Entry(row1, textvariable=self.search_var, width=22,
                  style="Dark.TEntry").pack(side="left")
        tk.Label(row1, text="Ordenar:", bg=BG, fg=FG_MUTED,
                 font=("", 10)).pack(side="left", padx=(12, 4))
        ttk.Combobox(row1, textvariable=self.sort_var, width=18,
                     values=["Nome", "Data da foto",
                             "Data de modificação", "Tamanho"],
                     state="readonly",
                     style="Dark.TCombobox").pack(side="left")
        row2 = tk.Frame(filters, bg=BG)
        row2.pack(fill="x", pady=(6, 0))
        ttk.Button(row2, text="Selecionar somente filtro",
                   style="Dark.TButton",
                   command=self.select_only_filter).pack(side="left",
                                                         padx=2)
        ttk.Button(row2, text="Marcar visíveis", style="Dark.TButton",
                   command=lambda: self.toggle_visible(True)).pack(
                       side="left", padx=2)
        ttk.Button(row2, text="Desmarcar visíveis",
                   style="Dark.TButton",
                   command=lambda: self.toggle_visible(False)).pack(
                       side="left", padx=2)
        tk.Label(row2, text="Filtrar não é selecionar: um arquivo "
                 "escondido pelo filtro continua marcado.",
                 bg=BG, fg=FG_MUTED, font=("", 10)).pack(side="left",
                                                          padx=10)

    def _update_filter_pills(self):
        if not hasattr(self, "filter_pills"):
            return
        current = self.filter_type.get()
        for label, btn in self.filter_pills.items():
            btn.configure(bg=ACCENT if label == current else BG_LIST)

    # ------------------------------------------------------------ conteudo

    def _build_content(self):
        content = tk.Frame(self.main, bg=BG)
        content.pack(fill="both", expand=True, padx=16, pady=4)
        # Grid com coluna direita FIXA (360px): a tabela encolhe, o
        # painel nunca e empurrado para fora da janela (com pack a
        # largura pedida pela Treeview empurrava o painel para alem
        # da borda direita, cortando chips e interruptores).
        content.columnconfigure(0, weight=1, minsize=0)
        content.columnconfigure(1, weight=0, minsize=350)
        content.rowconfigure(0, weight=1)
        # Tabela em cartao CLARO.
        card = tk.Frame(content, bg=LIGHT_BG)
        card.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        cols = ("sel", "original", "novo", "tipo", "data", "status")
        self.tree = ttk.Treeview(card, columns=cols,
                                 show="tree headings", selectmode="browse",
                                 style="Light.Treeview")
        self.tree.column("#0", width=60, stretch=False)
        self.tree.heading("#0", text="")
        widths = {"sel": 32, "original": 150, "novo": 185, "tipo": 56,
                  "data": 160, "status": 140}
        for col in cols:
            self.tree.heading(col, text={
                "sel": "✓", "original": "Arquivo Original",
                "novo": "Novo Nome (Prévia)", "tipo": "Tipo",
                "data": "Data",
                "status": "Status"}.get(col, col))
            self.tree.column(col, width=widths[col], stretch=True)
        self.tree.tag_configure("conflict", background="#FDE8E8",
                                foreground="#B91C1C")
        self.tree.tag_configure("nochange", foreground="#6B6480")
        scroll = ttk.Scrollbar(card, orient="vertical",
                               command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.tree.bind("<Button-1>", self.on_tree_click)
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)

        # Painel direito escuro (um painel por item da sidebar).
        right = tk.Frame(content, bg=BG_PANEL, width=350)
        right.grid(row=0, column=1, sticky="ns")
        right.pack_propagate(False)
        holder = tk.Frame(right, bg=BG_PANEL)
        holder.pack(fill="both", expand=True, padx=14, pady=12)
        self.panels = {
            "renomear": self._panel_padrao(holder),
            "presets": self._panel_presets(holder),
            "metadados": self._panel_metadados(holder),
            "regras": self._panel_regras(holder),
            "historico": self._panel_historico(holder),
            "config": self._panel_config(holder),
            "sobre": self._panel_sobre(holder),
        }

    # ------------------------------------------------- paineis (direita)

    def _section(self, parent, text):
        tk.Label(parent, text=text, bg=BG_PANEL, fg=FG,
                 font=("", 12, "bold")).pack(anchor="w", pady=(2, 8))

    def _field(self, parent, label, var, width=None):
        tk.Label(parent, text=label, bg=BG_PANEL, fg=FG_MUTED,
                 font=("", 10)).pack(anchor="w", pady=(8, 0))
        entry = ttk.Entry(parent, textvariable=var, style="Dark.TEntry")
        if width:
            entry.configure(width=width)
        entry.pack(fill="x")
        return entry

    def _spin(self, parent, var, from_=1, to=999999, width=7):
        # Empacota com anchor="w" (nunca side="left" direto no painel:
        # um widget side="left" reserva uma faixa a esquerda e empurra
        # todos os widgets seguintes para uma coluna estreita a direita).
        spin = tk.Spinbox(parent, from_=from_, to=to, width=width,
                          textvariable=var, bg=BG_LIST, fg=FG,
                          insertbackground=FG, buttonbackground="#3A2A63",
                          relief="flat")
        spin.pack(anchor="w")
        return spin

    def _panel_padrao(self, parent):
        tab = tk.Frame(parent, bg=BG_PANEL)
        self._section(tab, "Padrão de Renomeação")
        tk.Label(tab, text="Padrão:", bg=BG_PANEL, fg=FG_MUTED,
                 font=("", 10)).pack(anchor="w")
        combo = ttk.Combobox(tab, textvariable=self.padrao_combo_var,
                             values=["Personalizado"] +
                             [p["nome"] for p in DEFAULT_PRESETS],
                             state="readonly", style="Dark.TCombobox")
        combo.pack(fill="x", pady=(0, 4))
        combo.bind("<<ComboboxSelected>>", self._on_padrao_combo)
        tk.Label(tab, text="Estrutura do Novo Nome:", bg=BG_PANEL,
                 fg=FG, font=("", 10, "bold")).pack(anchor="w",
                                                    pady=(6, 0))
        self.pattern_entry = ttk.Entry(tab, textvariable=self.pattern_var,
                                       style="Dark.TEntry",
                                       font=("", 10))
        self.pattern_entry.pack(fill="x", pady=4)
        chips = tk.Frame(tab, bg=BG_PANEL)
        chips.pack(fill="x", pady=2)
        # Câmera insere {pasta} (nome da pasta-mãe = câmera/cartão);
        # Texto insere {nome} (nome original sem extensão).
        # Chips em duas linhas de 3: numa só linha o último chip
        # ("Texto") ficava cortado na borda direita do painel.
        for row_tokens in ((("Evento", "{evento}"), ("Tipo", "{tipo}"),
                            ("Data", "{datafoto}")),
                           (("Câmera", "{pasta}"),
                            ("Seq.", "{seq:0000}"), ("Texto", "{nome}"))):
            row = tk.Frame(chips, bg=BG_PANEL)
            row.pack(fill="x", pady=1)
            for label, token in row_tokens:
                tk.Button(row, text=label, bg=ACCENT, fg="white",
                          activebackground=ACCENT_LIGHT,
                          activeforeground="white", relief="flat",
                          font=("", 9, "bold"), padx=6, pady=3,
                          command=lambda t=token: self._insert_token(t)
                          ).pack(side="left", padx=2)
        tk.Label(tab, text="Evento e cliente: em Regras Avançadas.",
                 bg=BG_PANEL, fg=FG_MUTED, font=("", 9)).pack(
                     anchor="w", pady=(2, 4))
        tk.Label(tab, text="Numeração", bg=BG_PANEL, fg=FG,
                 font=("", 11, "bold")).pack(anchor="w", pady=(12, 4))
        num = tk.Frame(tab, bg=BG_PANEL)
        num.pack(fill="x")
        for label, var, width in (("Iniciar em", self.inicio_fotos_var, 6),
                                  ("Dígitos", self.digits_var, 3)):
            group = tk.Frame(num, bg=BG_PANEL)
            group.pack(side="left", padx=(0, 12))
            tk.Label(group, text=label, bg=BG_PANEL, fg=FG_MUTED,
                     font=("", 10)).pack(anchor="w")
            self._spin(group, var, width=width)
        group = tk.Frame(num, bg=BG_PANEL)
        group.pack(side="left")
        tk.Label(group, text="Tipo", bg=BG_PANEL, fg=FG_MUTED,
                 font=("", 10)).pack(anchor="w")
        ttk.Combobox(group, textvariable=self.numeracao_var,
                     values=["Crescente"], state="readonly", width=9,
                     style="Dark.TCombobox").pack(side="left")
        Toggle(tab, self.manter_extensao_var,
               "Manter extensão do arquivo", state="disabled").pack(
                   anchor="w", pady=(12, 4))
        Toggle(tab, self.data_arquivo_var,
               "Usar data do arquivo (quando aplicável)").pack(
                   anchor="w", pady=4)
        Toggle(tab, self.maiusculas_var,
               "Padronizar para MAIÚSCULAS").pack(anchor="w", pady=4)
        Toggle(tab, self.espacos_var,
               "Substituir espaços por _").pack(anchor="w", pady=4)
        tk.Label(tab, text="A extensão original é sempre mantida, "
                 "com a mesma caixa (.jpg fica .jpg).",
                 bg=BG_PANEL, fg=FG_MUTED, wraplength=315,
                 font=("", 9)).pack(anchor="w", pady=8)
        return tab

    def _panel_presets(self, parent):
        tab = tk.Frame(parent, bg=BG_PANEL)
        self._section(tab, "Presets")
        tk.Label(tab, text="Presets salvos (ficam neste PC, sem conta "
                 "e sem nuvem). Clique em Aplicar para usar um deles.",
                 bg=BG_PANEL, fg=FG_MUTED, wraplength=315,
                 font=("", 10)).pack(anchor="w")
        self.preset_list = tk.Listbox(tab, bg=BG_LIST, fg=FG,
                                      selectmode="browse", height=10,
                                      relief="flat",
                                      highlightthickness=0)
        self.preset_list.pack(fill="both", expand=True, pady=8)
        ttk.Button(tab, text="Aplicar preset", style="Accent.TButton",
                   command=self.apply_preset).pack(fill="x", pady=2)
        ttk.Button(tab, text="Salvar padrão atual como preset",
                   style="Dark.TButton",
                   command=self.save_preset).pack(fill="x", pady=2)
        ttk.Button(tab, text="Excluir preset", style="Dark.TButton",
                   command=self.delete_preset).pack(fill="x", pady=2)
        return tab

    def _panel_metadados(self, parent):
        tab = tk.Frame(parent, bg=BG_PANEL)
        self._section(tab, "Metadados (EXIF)")
        tk.Label(tab, text="Selecione um arquivo na lista para ver "
                 "a data EXIF, o tamanho e as dimensões.",
                 bg=BG_PANEL, fg=FG_MUTED, wraplength=315,
                 font=("", 10)).pack(anchor="w", pady=(0, 8))
        self.meta_text = tk.Text(tab, bg=BG_LIST, fg=FG, height=20,
                                 wrap="word", state="disabled",
                                 relief="flat")
        self.meta_text.pack(fill="both", expand=True)
        self._set_meta("Selecione um arquivo na lista para ver "
                       "a data EXIF, o tamanho e as dimensões.")
        return tab

    def _panel_regras(self, parent):
        tab = tk.Frame(parent, bg=BG_PANEL)
        self._section(tab, "Regras Avançadas")
        Toggle(tab, self.parear_var,
               "Parear JPG + RAW (mesmo número)").pack(anchor="w",
                                                       pady=4)
        self._field(tab, "Evento / prefixo:", self.evento_var)
        self._field(tab, "Cliente:", self.cliente_var)
        self._field(tab, "Tipo foto (JPG/RAW):", self.tipo_foto_var)
        self._field(tab, "Tipo vídeo:", self.tipo_video_var)
        tk.Label(tab, text="Início vídeos:", bg=BG_PANEL, fg=FG_MUTED,
                 font=("", 10)).pack(anchor="w", pady=(8, 0))
        self._spin(tab, self.inicio_videos_var)
        tk.Label(tab, text="Formato da data:", bg=BG_PANEL, fg=FG_MUTED,
                 font=("", 10)).pack(anchor="w", pady=(8, 0))
        ttk.Combobox(tab, textvariable=self.formato_data_var,
                     values=FORMATOS_DATA, state="readonly",
                     style="Dark.TCombobox").pack(fill="x")
        tk.Label(tab, text="Conflitos bloqueiam o lote: nome duplicado, "
                 "destino já existente, caractere inválido, nome "
                 "reservado do Windows ou nome com mais de 240 "
                 "caracteres. Resolva ou retire o arquivo da lista.",
                 bg=BG_PANEL, fg=FG_MUTED, wraplength=315,
                 font=("", 10)).pack(anchor="w", pady=12)
        tk.Label(tab, text="Localizar e substituir e regex ficam para "
                 "a v1.1. Por enquanto, use “Substituir espaços por _” "
                 "e “Padronizar para MAIÚSCULAS” no painel Padrão.",
                 bg=BG_PANEL, fg=FG_MUTED, wraplength=315,
                 font=("", 10)).pack(anchor="w")
        return tab

    def _panel_historico(self, parent):
        tab = tk.Frame(parent, bg=BG_PANEL)
        self._section(tab, "Histórico")
        self.history_empty_label = tk.Label(
            tab, text="Nenhum lote aplicado ainda.",
            bg=BG_PANEL, fg=FG_MUTED, font=("", 10))
        self.history_empty_label.pack(anchor="w")
        self.history_list = tk.Listbox(tab, bg=BG_LIST, fg=FG,
                                       selectmode="browse", height=8,
                                       relief="flat",
                                       highlightthickness=0)
        self.history_list.pack(fill="both", expand=True, pady=6)
        self.history_list.bind("<<ListboxSelect>>",
                               self.on_history_select)
        self.history_text = tk.Text(tab, bg=BG_LIST, fg=FG, height=12,
                                    wrap="word", state="disabled",
                                    relief="flat")
        self.history_text.pack(fill="both", expand=True)
        self._set_history_text(
            "Nenhum lote aplicado ainda.\n\nQuando você renomear um "
            "lote, ele aparece aqui com a data, a quantidade de "
            "arquivos e o detalhe de/para de cada um.")
        return tab

    def _panel_config(self, parent):
        tab = tk.Frame(parent, bg=BG_PANEL)
        self._section(tab, "Configurações")
        tk.Label(tab, text="Início fotos:", bg=BG_PANEL, fg=FG_MUTED,
                 font=("", 10)).pack(anchor="w", pady=(4, 0))
        self._spin(tab, self.inicio_fotos_var)
        tk.Label(tab, text="Início vídeos:", bg=BG_PANEL, fg=FG_MUTED,
                 font=("", 10)).pack(anchor="w", pady=(8, 0))
        self._spin(tab, self.inicio_videos_var)
        tk.Label(tab, text="Dígitos da sequência:", bg=BG_PANEL,
                 fg=FG_MUTED, font=("", 10)).pack(anchor="w",
                                                   pady=(8, 0))
        self._spin(tab, self.digits_var, from_=1, to=6, width=4)
        tk.Label(tab, text="Formato da data:", bg=BG_PANEL, fg=FG_MUTED,
                 font=("", 10)).pack(anchor="w", pady=(8, 0))
        ttk.Combobox(tab, textvariable=self.formato_data_var,
                     values=FORMATOS_DATA, state="readonly",
                     style="Dark.TCombobox").pack(fill="x")
        self._field(tab, "Tipo foto (JPG/RAW):", self.tipo_foto_var)
        self._field(tab, "Tipo vídeo:", self.tipo_video_var)
        tk.Label(tab, text="Dados locais (presets, logs e histórico):",
                 bg=BG_PANEL, fg=FG_MUTED, font=("", 10)).pack(
                     anchor="w", pady=(14, 0))
        tk.Label(tab, text=str(self.data), bg=BG_PANEL, fg=FG,
                 wraplength=315, font=("", 10)).pack(anchor="w")
        return tab

    def _panel_sobre(self, parent):
        tab = tk.Frame(parent, bg=BG_PANEL)
        self._section(tab, "Sobre")
        tk.Label(tab, text=f"DX Rename {VERSION} by DX Labs",
                 bg=BG_PANEL, fg=FG, font=("", 12, "bold")).pack(
                     anchor="w")
        tk.Label(tab, wraplength=315, justify="left", bg=BG_PANEL,
                 fg=FG, font=("", 10), text=
            "Renomeação em lote para fotos, RAW e vídeos. "
            "Padrão: {evento}_{tipo}_{seq:0000} — ex.: "
            "EXPO2026_FOTO_0001.JPG e EXPO2026_TAKE_0001.MP4. "
            "JPG e RAW do mesmo clique ganham o mesmo número. "
            "Conflitos bloqueiam o lote. Desfazer restaura o "
            "último lote pelo log de/para.\n\n"
            "O que NÃO faz: não move, copia ou apaga arquivos; "
            "não converte formato; não renomeia pastas; não "
            "usa nuvem, conta ou IA. Tudo roda local, offline.\n\n"
            "Repositório: rafarezende1974/takeid\n\n"
            "Teste primeiro numa pasta-cópia pequena (20–50 "
            "arquivos), nunca direto na pasta original.").pack(
                anchor="w", pady=8)
        return tab

    def _build_footer(self):
        footer = tk.Frame(self.main, bg=BG)
        footer.pack(side="bottom", fill="x", padx=16, pady=12)
        # Circulo verde com check, como no mockup.
        check = tk.Canvas(footer, width=32, height=32, bg=BG,
                          highlightthickness=0)
        check.pack(side="left")
        check.create_oval(2, 2, 30, 30, fill="#22C55E", outline="#22C55E")
        check.create_line(9, 16, 14, 22, 23, 10, fill="white", width=3)
        status = tk.Frame(footer, bg=BG)
        status.pack(side="left", padx=(10, 0))
        self.status_label = tk.Label(status, text="Nenhum arquivo",
                                     bg=BG, fg=FG, font=("", 11, "bold"))
        self.status_label.pack(anchor="w")
        self.status_sub_label = tk.Label(status, text="",
                                         bg=BG, fg=FG_MUTED,
                                         font=("", 10))
        self.status_sub_label.pack(anchor="w")
        self.undo_button = ttk.Button(footer, text="Desfazer último lote",
                                      style="Dark.TButton",
                                      command=self.do_undo)
        self.undo_button.pack(side="right", padx=4)
        self.rename_button = ttk.Button(footer, text="Renomear Arquivos",
                                        style="Big.Accent.TButton",
                                        command=self.do_rename)
        self.rename_button.pack(side="right", padx=4)

    # ------------------------------------------------- padrao / tokens

    def _insert_token(self, token):
        """Insere o token do chip no campo da estrutura, no cursor."""
        entry = self.pattern_entry
        try:
            entry.focus_set()
            pos = entry.index("insert")
        except tk.TclError:
            pos = "end"
        entry.insert(pos, token)

    def _apply_digits(self):
        """Dígitos da Numeração reescrevem o {seq:0000} do padrão."""
        if not hasattr(self, "pattern_var"):
            return
        try:
            digits = int(self.digits_var.get())
        except (tk.TclError, ValueError):
            return
        digits = max(1, min(6, digits))
        pat = self.pattern_var.get()
        new = re.sub(r"\{seq(?::[^}]*)?\}",
                     "{seq:" + "0" * digits + "}", pat)
        if new != pat:
            self.pattern_var.set(new)

    def _on_padrao_combo(self, _event=None):
        name = self.padrao_combo_var.get()
        if name == "Personalizado":
            return
        for preset in self.presets:
            if preset["nome"] == name:
                self.apply_settings(preset["settings"])
                return

    # ---------------------------------------------------------------- dados

    def _set_meta(self, text):
        self.meta_text.configure(state="normal")
        self.meta_text.delete("1.0", "end")
        self.meta_text.insert("1.0", text)
        self.meta_text.configure(state="disabled")

    def _set_history_text(self, text):
        self.history_text.configure(state="normal")
        self.history_text.delete("1.0", "end")
        self.history_text.insert("1.0", text)
        self.history_text.configure(state="disabled")

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
            messagebox.showinfo("DX Rename", "Os arquivos escolhidos já "
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
                self.status_sub_label.configure(text="")
                self.rename_button.configure(state="disabled")
            self.refresh_tree()
            return
        self.plan_by_path = {str(e.original_path): e for e in self.plan}
        self.refresh_tree()
        self.refresh_history()
        self._update_filter_pills()
        if not hasattr(self, "status_label"):
            return  # ainda construindo a janela (trace de um widget)
        total = len(self.items)
        sel = len(selected)
        conflicts = count_conflicts(self.plan)
        if sel:
            self.status_label.configure(
                text=f"{sel} arquivo(s) selecionado(s)")
        else:
            self.status_label.configure(text="Nenhum arquivo selecionado")
        if conflicts:
            sub = (f"{total} arquivo(s) na lista · {conflicts} com "
                   "conflito — resolva para liberar")
        elif sel:
            sub = (f"{total} arquivo(s) na lista · Novo nome válido "
                   "para todos os arquivos")
        elif total:
            sub = f"{total} arquivo(s) na lista · selecione arquivos"
        else:
            sub = "Adicione arquivos ou uma pasta para começar."
        self.status_sub_label.configure(text=sub)
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
                img.thumbnail((44, 44))
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
            messagebox.showinfo("DX Rename", "Escolha um preset na lista.")
            return
        preset = self.presets[sel[0]]
        self.apply_settings(preset["settings"])
        self.padrao_combo_var.set(preset["nome"])
        messagebox.showinfo("DX Rename",
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
        if not messagebox.askyesno("DX Rename",
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
        if not history:
            self.history_empty_label.configure(
                text="Nenhum lote aplicado ainda.")
            self._set_history_text(
                "Nenhum lote aplicado ainda.\n\nQuando você renomear "
                "um lote, ele aparece aqui com a data, a quantidade "
                "de arquivos e o detalhe de/para de cada um.")
        else:
            self.history_empty_label.configure(text="")

    def on_history_select(self, _event):
        sel = self.history_list.curselection()
        if not sel:
            return
        history = load_history(self.data)
        batch = history[sel[0]]
        lines = [f"{r['de']}  ->  {r['para']}"
                 for r in batch.get("arquivos", [])]
        self._set_history_text("\n".join(lines) or "Sem arquivos.")

    # -------------------------------------------------- renomear / desfazer

    def do_rename(self):
        selected = [e for e in self.plan if not e.no_change]
        if not selected:
            messagebox.showinfo("DX Rename", "Nada para renomear: os "
                                "arquivos selecionados já têm o nome "
                                "proposto.")
            return
        if has_conflicts(self.plan):
            messagebox.showwarning(
                "DX Rename", "Há conflitos na lista. Resolva ou retire "
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
            messagebox.showerror("DX Rename", str(exc))
            return
        if result["erros"]:
            messagebox.showwarning(
                "DX Rename",
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
        messagebox.showinfo("DX Rename — lote aplicado", msg)
        self.refresh()

    def do_undo(self):
        if not load_last_log(self.data):
            messagebox.showinfo("DX Rename", "Não há lote para desfazer.")
            return
        if not messagebox.askyesno(
                "Desfazer último lote",
                "Restaurar os nomes originais do último lote aplicado?"):
            return
        result = undo_last_batch(self.data)
        if result["erros"]:
            messagebox.showwarning(
                "DX Rename — desfazer parcial",
                f"{result['restaurados']} restaurado(s), "
                f"{result['pulados']} pulado(s).\n\n"
                + "\n".join(result["erros"]))
        else:
            messagebox.showinfo(
                "DX Rename", f"{result['restaurados']} arquivo(s) "
                "restaurado(s) com os nomes originais.")
        self.refresh()


def main():
    root = tk.Tk()
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
