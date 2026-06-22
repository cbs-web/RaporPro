import tkinter as tk
from tkinter import ttk


class UndoRedoEntry(ttk.Entry):
    def __init__(self, master=None, **kwargs):
        super().__init__(master, **kwargs)
        self.undo_stack = []
        self.redo_stack = []
        self.bind("<Control-z>", self.undo)
        self.bind("<Control-y>", self.redo)
        self.bind("<Key>", self.add_to_stack)
        self.bind("<FocusIn>", self.on_focus)
        self._last_value = self.get()
        self.undo_stack.append(self._last_value)

    def on_focus(self, event):
        pass

    def add_to_stack(self, event):
        if event.keysym in ("Control_L", "Control_R", "Alt_L", "Alt_R", "Shift_L", "Shift_R"):
            return
        self.after_idle(self._check_changes)

    def _check_changes(self):
        current_val = self.get()
        if current_val != self._last_value:
            self.undo_stack.append(current_val)
            self.redo_stack.clear()
            self._last_value = current_val
            if len(self.undo_stack) > 100:
                self.undo_stack.pop(0)

    def undo(self, event=None):
        if len(self.undo_stack) > 1:
            self.redo_stack.append(self.undo_stack.pop())
            prev_val = self.undo_stack[-1]
            self.delete(0, tk.END)
            self.insert(0, prev_val)
            self._last_value = prev_val
        return "break"

    def redo(self, event=None):
        if self.redo_stack:
            next_val = self.redo_stack.pop()
            self.undo_stack.append(next_val)
            self.delete(0, tk.END)
            self.insert(0, next_val)
            self._last_value = next_val
        return "break"
