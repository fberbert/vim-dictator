"""Ubuntu X11 tray application. Recording and transcription stay in the CLI."""

from __future__ import annotations

import argparse
import fcntl
import os
import signal
import subprocess
import sys
import threading
from pathlib import Path

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("AyatanaAppIndicator3", "0.1")
gi.require_version("Keybinder", "3.0")
from gi.repository import AyatanaAppIndicator3, Gdk, GLib, Gtk, Keybinder

from vim_dictator_desktop import DesktopBackend, paste_shortcut


DEFAULT_HOTKEY = "<Ctrl><Alt>space"
BUSY_PHASES = {"starting", "transcribing", "cancelling", "pasting"}


def copy_text(text: str) -> None:
    clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
    clipboard.set_text(text, -1)


def paste_into_focus() -> None:
    focused = subprocess.run(
        ["xdotool", "getwindowfocus"],
        capture_output=True, text=True, check=False, timeout=5,
    )
    if focused.returncode or not focused.stdout.strip().isdigit():
        raise RuntimeError("Não foi possível identificar o aplicativo em foco. O texto foi copiado.")
    window_class = subprocess.run(
        ["xprop", "-id", focused.stdout.strip(), "WM_CLASS"],
        capture_output=True, text=True, check=False, timeout=5,
    )
    if window_class.returncode or "=" not in window_class.stdout:
        raise RuntimeError("Não foi possível identificar o aplicativo em foco. O texto foi copiado.")
    pasted = subprocess.run(
        ["xdotool", "key", "--clearmodifiers", paste_shortcut(window_class.stdout)],
        capture_output=True, text=True, check=False, timeout=5,
    )
    if pasted.returncode:
        raise RuntimeError("Não foi possível colar. Use Copiar última transcrição.")


class TrayApp:
    def __init__(self, backend=None, hotkey=DEFAULT_HOTKEY, paste=None, on_quit=None):
        self.backend = backend or DesktopBackend()
        self.paste = paste or paste_into_focus
        self.on_quit = on_quit or Gtk.main_quit
        self.hotkey = hotkey
        self.bound = False
        self.quit_requested = False
        self.last_text = ""
        self.phase = "retry" if self.backend.has_session() else "idle"
        self.indicator = AyatanaAppIndicator3.Indicator.new(
            "vim-dictator-x", "audio-input-microphone", AyatanaAppIndicator3.IndicatorCategory.APPLICATION_STATUS,
        )
        self.indicator.set_title("Vim Dictator")
        self.menu = Gtk.Menu()
        self.status_item = self._item("Pronto para ditar")
        self.status_item.set_sensitive(False)
        self.toggle_item = self._item("Iniciar ditado", self.toggle)
        self.cancel_item = self._item("Cancelar ditado", self.cancel)
        self.copy_item = self._item("Copiar última transcrição", self.copy_last)
        self._item("Sair", self.quit)
        self.indicator.set_menu(self.menu)
        self.indicator.set_status(AyatanaAppIndicator3.IndicatorStatus.ACTIVE)
        self._refresh()
        if hotkey:
            Keybinder.init()
            self.bound = Keybinder.bind(hotkey, self.toggle, None)
            label = Gtk.accelerator_get_label(*Gtk.accelerator_parse(hotkey))
            shortcut_item = self._item("Atalho: " + label)
            shortcut_item.set_sensitive(False)
            if not self.bound:
                self.status_item.set_label("Atalho ocupado; use o menu ou escolha outro com --hotkey.")
        self.menu.show_all()

    def _item(self, label, callback=None):
        item = Gtk.MenuItem.new_with_label(label)
        if callback:
            item.connect("activate", callback)
        self.menu.append(item)
        return item

    def _refresh(self, message=None):
        descriptions = {
            "idle": "Pronto para ditar", "starting": "Iniciando microfone…",
            "recording": "Gravando…", "transcribing": "Transcrevendo…",
            "retry": "Áudio preservado: tente novamente ou cancele",
            "cancelling": "Cancelando…", "pasting": "Colando…", "closed": "Encerrado",
        }
        self.status_item.set_label(message or descriptions[self.phase])
        self.toggle_item.set_label({
            "recording": "Parar e colar", "retry": "Tentar transcrição",
        }.get(self.phase, "Iniciar ditado"))
        self.toggle_item.set_sensitive(self.phase in {"idle", "recording", "retry"})
        self.cancel_item.set_sensitive(self.phase in {"recording", "retry"})
        self.copy_item.set_sensitive(bool(self.last_text))
        icon = "media-record" if self.phase == "recording" else "audio-input-microphone"
        self.indicator.set_icon_full(icon, descriptions[self.phase])
        self.indicator.set_label("Gravando" if self.phase == "recording" else "", "Gravando")

    def _run(self, action):
        self.phase = {"start": "starting", "stop": "transcribing", "cancel": "cancelling"}[action]
        self._refresh()

        def work():
            try:
                text, error = self.backend.run(action), None
            except Exception as failure:
                text, error = "", str(failure)
            GLib.idle_add(self._completed, action, text, error)

        threading.Thread(target=work, daemon=True, name="vim-dictator-" + action).start()

    def toggle(self, *_args):
        if self.phase == "idle":
            self._run("start")
        elif self.phase in {"recording", "retry"}:
            self._run("stop")

    def cancel(self, *_args):
        if self.phase in {"recording", "retry"}:
            self._run("cancel")

    def _completed(self, action, text, error):
        if error:
            self.phase = "idle" if action == "start" else "retry"
            self._refresh(error)
            if action == "cancel":
                self.quit_requested = False
        else:
            self.phase = "recording" if action == "start" else "idle"
            if action == "stop" and text.strip() and not self.quit_requested:
                self.last_text = text
                self.phase = "pasting"
                try:
                    copy_text(text)
                except Exception as failure:
                    self.phase = "idle"
                    self._refresh(str(failure) + " — use Copiar última transcrição.")
                    return False
                # Serve clipboard requests before the terminal enables its paste action.
                GLib.timeout_add(250, self._paste)
            self._refresh("A transcrição veio vazia." if action == "stop" and not text.strip() else None)
        if self.quit_requested:
            self.quit()
        return False

    def _paste(self):
        if self.quit_requested:
            self.phase = "idle"
            self.quit()
            return False
        def work():
            try:
                self.paste()
                message = "Texto enviado ao aplicativo em foco."
            except Exception as error:
                message = str(error) + " — use Copiar última transcrição."
            GLib.idle_add(self._paste_completed, message)

        threading.Thread(target=work, daemon=True, name="vim-dictator-paste").start()
        return False

    def _paste_completed(self, message):
        self.phase = "idle"
        self._refresh(message)
        if self.quit_requested:
            self.quit()
        return False

    def copy_last(self, *_args):
        if self.last_text:
            copy_text(self.last_text)
            self._refresh("Última transcrição copiada.")

    def quit(self, *_args):
        self.quit_requested = True
        if self.phase in BUSY_PHASES:
            self.status_item.set_label("Encerrando após a operação atual…")
        elif self.phase in {"recording", "retry"}:
            self._run("cancel")
        else:
            self.close()
            self.on_quit()
        return False

    def close(self):
        if self.phase == "closed":
            return
        if self.bound:
            Keybinder.unbind(self.hotkey)
        self.indicator.set_status(AyatanaAppIndicator3.IndicatorStatus.PASSIVE)
        self.menu.destroy()
        self.indicator = None
        self.phase = "closed"


def main(arguments=None):
    parser = argparse.ArgumentParser(description="Ditado na bandeja do Ubuntu (X11).")
    parser.add_argument("--hotkey", default=DEFAULT_HOTKEY, help="Atalho GTK, padrão: <Ctrl><Alt>space")
    parser.add_argument("--no-hotkey", action="store_true", help="Usar apenas o menu da bandeja")
    options = parser.parse_args(arguments)
    if os.environ.get("XDG_SESSION_TYPE") == "wayland":
        parser.error("A inserção automática requer uma sessão Ubuntu on Xorg (X11).")
    if not Gtk.init_check()[0]:
        parser.error("Não foi possível abrir o desktop. Execute em um terminal da sessão gráfica.")
    if "X11" not in Gdk.Display.get_default().__gtype__.name:
        parser.error("A inserção automática requer X11.")
    if not options.no_hotkey and not Gtk.accelerator_parse(options.hotkey)[0]:
        parser.error("Atalho inválido. Exemplo: --hotkey '<Ctrl><Alt>space'")
    backend = DesktopBackend()
    runtime = Path(backend.env["VIM_DICTATOR_RUNTIME_DIR"])
    runtime.mkdir(mode=0o700, parents=True, exist_ok=True)
    with (runtime / "tray.lock").open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print("Vim Dictator já está aberto na bandeja.", file=sys.stderr)
            return 1
        app = TrayApp(backend, hotkey=None if options.no_hotkey else options.hotkey)
        for signal_number in (signal.SIGINT, signal.SIGTERM):
            GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, signal_number, app.quit)
        try:
            Gtk.main()
        finally:
            app.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
