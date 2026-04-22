import os
import flet as ft
from app.theme import Colors, Fonts
from app.services.segment_aligner import SegmentAligner


class ParallelView:
    """Side-by-side parallel view of German source and English translation.

    Accepts the same ``translation_data`` dict that ``TranslationResultTab``
    uses, so it can be swapped in as a drop-in replacement.
    """

    def __init__(self, translation_data: dict, page: ft.Page = None, actions: dict = None):
        self.translation_data = translation_data
        self._page = page
        self._actions = actions or {}

        # Align source ↔ translation into segment pairs
        source_full = translation_data.get("source_full", "")
        translation = translation_data.get("translation", "")
        aligner = SegmentAligner()
        self.segments = aligner.align(source_full, translation)

        # Segment container references for highlight toggling
        self._source_containers: list[ft.Container] = []
        self._translation_containers: list[ft.Container] = []
        self._active_index: int = -1

        # Scrollable inner column references for scroll_to support
        self._source_scroll_col: ft.Column | None = None
        self._translation_scroll_col: ft.Column | None = None

        # Re-entrancy guard for synchronized scrolling
        self._syncing: bool = False

        # Optional commentary / metrics carried over from the old tab
        self.commentary = translation_data.get("commentary")
        self.metrics = translation_data.get("metrics")

        # Create metrics footer if available
        self.metrics_footer = None
        if self.metrics:
            self.metrics_footer = self._create_metrics_footer(self.metrics)

        # PDF source path (if translation originated from a PDF)
        self.pdf_path = translation_data.get("pdf_path")
        self._pdf_viewer = None

        # File picker for re-locating a missing PDF
        self._file_picker = ft.FilePicker(on_result=self._on_pdf_relocated)
        if self._page is not None:
            self._page.overlay.append(self._file_picker)

        # Reference to the parallel row so _on_pdf_relocated can swap the left column
        self._parallel_row: ft.Row | None = None

        # Reference to the built control tree for cleanup
        self._built_tree: ft.Column | None = None

        # --- HITL state ---
        self._tab_id = translation_data.get("id", 0)
        self._editing_segment: int = -1       # segment currently in CorrectionEditor
        self._retranslate_segment: int = -1   # segment showing re-translate instructions

        # HITL services from actions
        self._version_store = self._actions.get("version_store")
        self._re_translation_engine = self._actions.get("re_translation_engine")
        self._correction_service = self._actions.get("correction_service")
        # Lazy getter — avoids loading BERT until correction is actually committed
        self._get_correction_service = self._actions.get("get_correction_service")
        self._bus = self._actions.get("bus")
        self._settings = self._actions.get("settings")

        # DiffView overlay reference (shown per-segment)
        self._diff_overlay: ft.Control | None = None
        self._diff_overlay_segment: int = -1

        # VersionNav control references per segment
        self._version_nav_rows: dict[int, ft.Row] = {}

        # Initialize VersionStore from segments (seed v1 for each)
        if self._version_store and self.segments:
            self._version_store.initialize_from_segments(self._tab_id, self.segments)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _format_time(self) -> str:
        """Safely format the timestamp."""
        ts = self.translation_data.get("timestamp")
        if ts is None:
            return ""
        try:
            if hasattr(ts, "strftime"):
                return ts.strftime("%H:%M:%S")
            from datetime import datetime
            return datetime.fromisoformat(str(ts)).strftime("%H:%M:%S")
        except Exception:
            return ""

    def _create_metrics_footer(self, metrics: dict) -> ft.Container:
        """Create metrics footer display (same pattern as TranslationResultTab)."""
        cost = metrics.get("estimated_cost", 0)
        input_tokens = metrics.get("input_tokens", 0)
        output_tokens = metrics.get("output_tokens", 0)
        total_tokens = input_tokens + output_tokens
        model_used = metrics.get("model_used", "Unknown")

        return ft.Container(
            content=ft.Row(
                controls=[
                    ft.Text(f"💰 ${cost}", size=12, color=Colors.INK_MUTED, font_family=Fonts.MONO),
                    ft.Text("•", size=12, color=Colors.INK_MUTED),
                    ft.Text(
                        f"🎯 {total_tokens} tokens ({input_tokens}→{output_tokens})",
                        size=12, color=Colors.INK_MUTED, font_family=Fonts.MONO,
                    ),
                    ft.Text("•", size=12, color=Colors.INK_MUTED),
                    ft.Text(f"🤖 {model_used}", size=12, color=Colors.INK_MUTED, font_family=Fonts.MONO),
                    ft.Container(expand=True),
                    ft.Text(f"📅 {self._format_time()}", size=12, color=Colors.INK_MUTED, font_family=Fonts.MONO),
                ],
                spacing=8,
                alignment=ft.MainAxisAlignment.START,
            ),
            padding=ft.padding.symmetric(horizontal=24, vertical=12),
            bgcolor=Colors.SURFACE,
            border=ft.border.only(top=ft.BorderSide(1, Colors.DIVIDER)),
        )

    def _build_commentary_section(self) -> list[ft.Control]:
        """Build the ornamental divider and commentary markdown section.

        Returns a list of controls to append to the scrollable content area.
        """
        if not self.commentary:
            return []

        commentary_markdown = ft.Markdown(
            value=self.commentary,
            selectable=True,
            extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
            code_theme="monokai",
            code_style=ft.TextStyle(font_family=Fonts.MONO, size=14, color=Colors.GOLD),
        )

        # Ornamental divider
        divider = ft.Container(
            content=ft.Row(
                controls=[
                    ft.Container(
                        content=ft.Container(bgcolor=Colors.GOLD, height=1, opacity=0.4),
                        expand=True,
                    ),
                    ft.Text(
                        "❦ Philological Commentary ❦",
                        size=16, color=Colors.GOLD, font_family=Fonts.SERIF, opacity=0.9,
                    ),
                    ft.Container(
                        content=ft.Container(bgcolor=Colors.GOLD, height=1, opacity=0.4),
                        expand=True,
                    ),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                spacing=16,
            ),
            padding=ft.padding.symmetric(horizontal=24, vertical=20),
        )

        # Commentary content
        commentary_section = ft.Container(
            content=ft.Column(
                controls=[
                    ft.Container(
                        content=ft.Text(
                            "Commentary",
                            size=20, color=Colors.GOLD, font_family=Fonts.HEADER, weight=ft.FontWeight.W_500,
                        ),
                        padding=ft.padding.only(bottom=16),
                    ),
                    ft.Container(
                        content=commentary_markdown,
                        bgcolor=Colors.SURFACE,
                        border_radius=8,
                        padding=ft.padding.all(20),
                        border=ft.border.all(1, Colors.DIVIDER),
                    ),
                ],
                spacing=0,
            ),
            padding=ft.padding.symmetric(horizontal=24, vertical=0),
        )

        return [divider, commentary_section]

    def _on_segment_tap(self, index: int, side: str):
        """Handle a tap on a segment. Highlights both source and translation at *index*."""
        # Clear previous highlight
        if self._active_index >= 0:
            prev_src = self._source_containers[self._active_index]
            prev_trl = self._translation_containers[self._active_index]
            prev_src.bgcolor = Colors.SURFACE
            prev_src.border = ft.border.only(bottom=ft.BorderSide(1, Colors.DIVIDER))
            prev_trl.bgcolor = Colors.SURFACE
            prev_trl.border = ft.border.only(bottom=ft.BorderSide(1, Colors.DIVIDER))
            prev_src.update()
            prev_trl.update()

        # Apply new highlight
        self._active_index = index
        src = self._source_containers[index]
        trl = self._translation_containers[index]
        highlight_border = ft.border.only(
            left=ft.BorderSide(3, Colors.GOLD),
            bottom=ft.BorderSide(1, Colors.DIVIDER),
        )
        src.bgcolor = Colors.SURFACE_RAISED
        src.border = highlight_border
        trl.bgcolor = Colors.SURFACE_RAISED
        trl.border = highlight_border
        src.update()
        trl.update()

        # Scroll the opposite column to bring the corresponding segment into view
        try:
            if side == "source" and self._translation_scroll_col:
                self._translation_scroll_col.scroll_to(key=f"seg_translation_{index}")
            elif side == "translation" and self._source_scroll_col:
                self._source_scroll_col.scroll_to(key=f"seg_source_{index}")
        except Exception:
            pass  # scroll_to may fail if column hasn't rendered yet

    def _on_source_scroll(self, e: ft.OnScrollEvent):
        """Mirror source column scroll position to translation column."""
        if self._syncing:
            return
        self._syncing = True
        try:
            src_max = e.max_scroll_extent
            if src_max > 0 and self._translation_scroll_col:
                pct = e.pixels / src_max
                # Clamp to the translation column's own extent so the
                # shorter side stops at its bottom instead of locking up.
                tgt_max = getattr(self._translation_scroll_col, '_max_scroll_extent', src_max)
                offset = min(pct * tgt_max, tgt_max)
                self._translation_scroll_col.scroll_to(
                    offset=offset, duration=0,
                )
        except Exception:
            pass
        finally:
            import threading
            threading.Timer(0.05, self._clear_syncing).start()

    def _on_translation_scroll(self, e: ft.OnScrollEvent):
        """Mirror translation column scroll position to source column."""
        if self._syncing:
            return
        self._syncing = True
        try:
            tgt_max = e.max_scroll_extent
            if tgt_max > 0 and self._source_scroll_col:
                pct = e.pixels / tgt_max
                src_max = getattr(self._source_scroll_col, '_max_scroll_extent', tgt_max)
                offset = min(pct * src_max, src_max)
                self._source_scroll_col.scroll_to(
                    offset=offset, duration=0,
                )
        except Exception:
            pass
        finally:
            import threading
            threading.Timer(0.05, self._clear_syncing).start()

    def _clear_syncing(self):
        """Reset the scroll sync guard after a short delay."""
        self._syncing = False

    def _on_segment_right_click(self, e, index: int, side: str):
        """Handle right-click on a segment to open a pre-filled Pin Term dialog.

        Extracts the German source text and its corresponding English translation
        from the clicked segment pair and opens the Add Term dialog pre-filled
        with both values so the user can refine before saving.
        """
        if not self._page:
            return

        # Get the text from the segment pair
        source_text = ""
        translation_text = ""
        if index < len(self.segments):
            source_text = self.segments[index].source_text
            translation_text = self.segments[index].translation_text

        # Open the pre-filled Add Term dialog immediately
        self._show_pin_term_dialog(source_text, translation_text)

    def _show_pin_term_dialog(self, german_prefill: str = "", english_prefill: str = "", pin_after_save: bool = False):
        """Show the Pin Term to Glossary dialog pre-filled with segment text.

        If *pin_after_save* is True, the saved term is also pinned to the sidebar
        and the sidebar glossary display is refreshed.
        """
        from app.theme import UI

        glossary_mgr = self._actions.get("glossary_manager")
        if not glossary_mgr:
            if self._page and hasattr(self._page, 'bus'):
                pass  # No bus-based banner available directly
            return

        german_field = ft.TextField(
            value=german_prefill,
            hint_text="e.g. Geist",
            border_color=Colors.DIVIDER,
            focused_border_color=Colors.GOLD,
            color=Colors.INK,
            text_size=14,
        )
        english_field = ft.TextField(
            value=english_prefill,
            hint_text="e.g. Spirit",
            border_color=Colors.DIVIDER,
            focused_border_color=Colors.GOLD,
            color=Colors.INK,
            text_size=14,
        )
        context_target_field = ft.TextField(
            hint_text="e.g. deconstruct",
            border_color=Colors.DIVIDER,
            focused_border_color=Colors.GOLD,
            color=Colors.INK,
            text_size=14,
        )
        field_tag_field = ft.TextField(
            hint_text="e.g. Philosophy, Legal, Science…",
            border_color=Colors.DIVIDER,
            focused_border_color=Colors.GOLD,
            color=Colors.INK,
            text_size=14,
        )
        nuance_note_field = ft.TextField(
            hint_text="Briefly explain the semantic shift…",
            multiline=True,
            border_color=Colors.DIVIDER,
            focused_border_color=Colors.GOLD,
            color=Colors.INK,
            text_size=14,
        )
        error_text = ft.Text("", size=11, color=Colors.DESTRUCTIVE, visible=False)

        def on_save(dialog_e):
            try:
                german = german_field.value.strip() if german_field.value else ""
                english = english_field.value.strip() if english_field.value else ""
                context_target = context_target_field.value.strip() if context_target_field.value else ""
                field_tag = field_tag_field.value.strip() if field_tag_field.value else ""
                nuance_note = nuance_note_field.value.strip() if nuance_note_field.value else ""

                if not german or not english:
                    error_text.value = "German and English fields are required."
                    error_text.visible = True
                    self._page.update()
                    return

                glossary_mgr.add_term(german, english, context_target, field_tag, nuance_note)
                pin_dialog.open = False
                self._page.update()

                # Pin to sidebar if requested
                if pin_after_save:
                    glossary_mgr.pin_term(german)
                    refresh = self._actions.get("refresh_glossary_sidebar")
                    if refresh:
                        refresh()

                # Show confirmation via banner if bus is available
                bus = self._actions.get("bus")
                if bus:
                    pin_label = " & pinned to sidebar" if pin_after_save else ""
                    bus.show_banner(f"📌 Pinned: {german} → {english}{pin_label}")
            except Exception as exc:
                error_text.value = f"Error: {exc}"
                error_text.visible = True
                self._page.update()

        def on_cancel(dialog_e):
            pin_dialog.open = False
            self._page.update()

        pin_dialog = ft.AlertDialog(
            modal=True,
            title=ft.Text("Pin Term to Glossary", font_family=Fonts.HEADER, size=18, color=Colors.GOLD),
            content=ft.Column([
                ft.Text("German Term *", size=12, color=Colors.INK_MUTED),
                german_field,
                ft.Text("English (default equivalent) *", size=12, color=Colors.INK_MUTED),
                english_field,
                ft.Text("Context-Sensitive Target", size=12, color=Colors.INK_MUTED),
                context_target_field,
                ft.Text("Field Tag", size=12, color=Colors.INK_MUTED),
                field_tag_field,
                ft.Text("Nuance Note", size=12, color=Colors.INK_MUTED),
                nuance_note_field,
                error_text,
            ], spacing=8, tight=True, width=340, scroll=ft.ScrollMode.AUTO),
            actions=[
                ft.TextButton(content=ft.Text("Cancel", font_family=Fonts.FRAKTUR), on_click=on_cancel),
                ft.ElevatedButton(content=ft.Text("Save", font_family=Fonts.FRAKTUR, weight="bold"), on_click=on_save, bgcolor=Colors.GOLD, color=Colors.BACKGROUND),
            ],
            bgcolor=Colors.SURFACE,
            shape=ft.RoundedRectangleBorder(radius=12),
        )

        self._page.dialog = pin_dialog
        pin_dialog.open = True
        self._page.update()

    def _build_segment(self, text: str, index: int, side: str) -> ft.GestureDetector:
        """Build a single segment wrapped in a GestureDetector for click handling.

        For translation-side segments, adds HITL affordances:
        - Re-translate icon button
        - VersionNav (visible when versions > 1)
        - Double-click to activate CorrectionEditor

        For source-side segments, adds:
        - "Add to Glossary" icon button
        - "Add to Glossary & Pin" icon button (adds term and pins to sidebar)
        """
        text_control = ft.Text(
            text,
            size=16,
            font_family=Fonts.SERIF,
            color=Colors.INK,
            selectable=True,
            style=ft.TextStyle(height=1.75),
        )

        # For translation side, build a richer layout with HITL controls
        if side == "translation":
            content_controls: list[ft.Control] = [text_control]

            # VersionNav row (only visible when versions > 1)
            version_nav_row = self._build_version_nav(index)
            if version_nav_row:
                content_controls.append(version_nav_row)

            # Re-translate button row
            retranslate_btn = ft.IconButton(
                icon=ft.Icons.REFRESH,
                icon_size=14,
                icon_color=Colors.INK_MUTED,
                tooltip="Re-translate this segment",
                on_click=lambda e, idx=index: self._on_retranslate_click(idx),
                style=ft.ButtonStyle(padding=ft.padding.all(0)),
                width=24,
                height=24,
            )

            header_row = ft.Row(
                controls=[ft.Container(expand=True), retranslate_btn],
                spacing=4,
                alignment=ft.MainAxisAlignment.END,
            )
            content_controls.insert(0, header_row)

            inner_content = ft.Column(controls=content_controls, spacing=4)
        elif side == "source":
            # Source side: add glossary action buttons
            add_glossary_btn = ft.IconButton(
                icon=ft.Icons.BOOKMARK_ADD,
                icon_size=14,
                icon_color=Colors.INK_MUTED,
                tooltip="Add to Glossary",
                on_click=lambda e, idx=index: self._on_add_to_glossary(idx),
                style=ft.ButtonStyle(padding=ft.padding.all(0)),
                width=24,
                height=24,
            )
            add_glossary_pin_btn = ft.IconButton(
                icon=ft.Icons.PUSH_PIN_OUTLINED,
                icon_size=14,
                icon_color=Colors.INK_MUTED,
                tooltip="Add to Glossary & Pin to Sidebar",
                on_click=lambda e, idx=index: self._on_add_to_glossary_and_pin(idx),
                style=ft.ButtonStyle(padding=ft.padding.all(0)),
                width=24,
                height=24,
            )
            header_row = ft.Row(
                controls=[ft.Container(expand=True), add_glossary_btn, add_glossary_pin_btn],
                spacing=4,
                alignment=ft.MainAxisAlignment.END,
            )
            inner_content = ft.Column(controls=[header_row, text_control], spacing=4)
        else:
            inner_content = text_control

        container = ft.Container(
            content=inner_content,
            bgcolor=Colors.SURFACE,
            padding=ft.padding.symmetric(horizontal=24, vertical=12),
            border=ft.border.only(bottom=ft.BorderSide(1, Colors.DIVIDER)),
            data={"index": index, "side": side},
        )

        # Store reference so highlight logic can mutate the container later
        if side == "source":
            self._source_containers.append(container)
        else:
            self._translation_containers.append(container)

        # Build gesture detector — translation side gets double-tap for editing
        if side == "translation":
            return ft.GestureDetector(
                content=container,
                on_tap=lambda e, idx=index, s=side: self._on_segment_tap(idx, s),
                on_secondary_tap=lambda e, idx=index, s=side: self._on_segment_right_click(e, idx, s),
                on_double_tap=lambda e, idx=index: self._on_double_tap_translation(idx),
                key=f"seg_{side}_{index}",
            )
        else:
            return ft.GestureDetector(
                content=container,
                on_tap=lambda e, idx=index, s=side: self._on_segment_tap(idx, s),
                on_secondary_tap=lambda e, idx=index, s=side: self._on_segment_right_click(e, idx, s),
                key=f"seg_{side}_{index}",
            )

    # ------------------------------------------------------------------
    # HITL handlers
    # ------------------------------------------------------------------

    def _on_add_to_glossary(self, index: int):
        """Open the Add to Glossary dialog pre-filled with the source/translation pair."""
        source_text = ""
        translation_text = ""
        if index < len(self.segments):
            source_text = self.segments[index].source_text
            translation_text = self.segments[index].translation_text
        self._show_pin_term_dialog(source_text, translation_text)

    def _on_add_to_glossary_and_pin(self, index: int):
        """Open the Add to Glossary dialog; on save, also pin the term to the sidebar."""
        source_text = ""
        translation_text = ""
        if index < len(self.segments):
            source_text = self.segments[index].source_text
            translation_text = self.segments[index].translation_text
        self._show_pin_term_dialog(source_text, translation_text, pin_after_save=True)

    def _build_version_nav(self, index: int) -> ft.Control | None:
        """Build a VersionNav row for a segment. Returns None if no version_store."""
        if not self._version_store:
            return None

        from app.components.widgets.version_nav import VersionNav

        nav = VersionNav(
            tab_id=self._tab_id,
            segment_index=index,
            version_store=self._version_store,
            on_compare=self._on_compare,
            on_accept=self._on_accept,
        )
        row = nav.build()
        self._version_nav_rows[index] = row
        return row

    def _on_retranslate_click(self, index: int):
        """Show an instructions TextField pre-filled with thematic_focus for re-translation."""
        if self._retranslate_segment == index:
            # Toggle off — hide the instructions input
            self._retranslate_segment = -1
            self._restore_translation_segment(index)
            return

        self._retranslate_segment = index

        # Get current thematic focus as default instructions
        thematic_focus = ""
        if self._settings:
            thematic_focus = self._settings.get_thematic_focus()

        instructions_field = ft.TextField(
            value=thematic_focus,
            hint_text="Instructions for re-translation…",
            multiline=True,
            min_lines=2,
            max_lines=4,
            bgcolor=Colors.SURFACE,
            color=Colors.FOREGROUND,
            border_color=Colors.DIVIDER,
            focused_border_color=Colors.GOLD,
            cursor_color=Colors.GOLD,
            text_style=ft.TextStyle(size=13, font_family=Fonts.SERIF),
            content_padding=ft.padding.all(8),
            border_radius=6,
            expand=True,
        )

        go_btn = ft.TextButton(
            text="Go",
            style=ft.ButtonStyle(color=Colors.GOLD, text_style=ft.TextStyle(font_family=Fonts.FRAKTUR)),
            on_click=lambda e, idx=index, field=instructions_field: self._do_retranslate(idx, field),
        )
        cancel_btn = ft.TextButton(
            text="Cancel",
            style=ft.ButtonStyle(color=Colors.INK_MUTED, text_style=ft.TextStyle(font_family=Fonts.FRAKTUR)),
            on_click=lambda e, idx=index: self._cancel_retranslate(idx),
        )

        instructions_row = ft.Column(
            controls=[
                ft.Text("Re-translate instructions:", size=11, color=Colors.INK_MUTED),
                instructions_field,
                ft.Row(controls=[go_btn, cancel_btn], spacing=8),
            ],
            spacing=4,
        )

        # Replace the translation container content with instructions input
        container = self._translation_containers[index]
        # Preserve the original text above the instructions
        original_text = self._get_segment_translation_text(index)
        container.content = ft.Column(
            controls=[
                ft.Text(
                    original_text,
                    size=16, font_family=Fonts.SERIF, color=Colors.INK,
                    selectable=True, style=ft.TextStyle(height=1.75),
                ),
                instructions_row,
            ],
            spacing=8,
        )
        try:
            container.update()
        except Exception:
            pass

    def _do_retranslate(self, index: int, instructions_field: ft.TextField):
        """Execute re-translation for a segment."""
        if not self._re_translation_engine:
            if self._bus:
                self._bus.show_banner("Re-translation engine not available.", is_error=True)
            return

        instructions = instructions_field.value or ""
        source_text = self.segments[index].source_text if index < len(self.segments) else ""

        # Get glossary block if available
        glossary_mgr = self._actions.get("glossary_manager")
        glossary_block = glossary_mgr.get_prompt_block() if glossary_mgr else ""

        self._retranslate_segment = -1

        # Run re-translation (runs in background thread, blocks until done)
        self._re_translation_engine.re_translate(
            source_text=source_text,
            instructions=instructions,
            tab_id=self._tab_id,
            segment_index=index,
            glossary_block=glossary_block,
        )

        # Refresh the segment display with the new version
        self._refresh_translation_segment(index)

    def _cancel_retranslate(self, index: int):
        """Cancel re-translate instructions input and restore segment."""
        self._retranslate_segment = -1
        self._restore_translation_segment(index)

    def _on_double_tap_translation(self, index: int):
        """Activate CorrectionEditor for a translation segment on double-click."""
        if self._editing_segment == index:
            return  # Already editing this segment

        from app.components.widgets.correction_editor import CorrectionEditor

        current_text = self._get_segment_translation_text(index)
        self._editing_segment = index

        def on_save(edited_text: str):
            self._editing_segment = -1
            # Add version with is_manual=True
            if self._version_store:
                version = self._version_store.add_version(
                    tab_id=self._tab_id,
                    segment_index=index,
                    text=edited_text,
                    is_manual=True,
                )
                if version is not None:
                    # Update translation_tabs in AppState
                    self._update_translation_tab_text(index, edited_text)
                    # Show CommitToMemoryPrompt
                    self._show_commit_to_memory(index, current_text, edited_text)

            # Refresh the segment display
            self._refresh_translation_segment(index)

        def on_cancel():
            self._editing_segment = -1
            self._restore_translation_segment(index)

        editor = CorrectionEditor(
            current_text=current_text,
            on_save=on_save,
            on_cancel=on_cancel,
        )

        # Replace container content with the editor
        container = self._translation_containers[index]
        container.content = editor.build()
        try:
            container.update()
        except Exception:
            pass

    def _show_commit_to_memory(self, index: int, original_text: str, corrected_text: str):
        """Show CommitToMemoryPrompt after a manual correction save."""
        if not self._page:
            return

        # Lazily resolve CorrectionService (and thus BERT) on first use
        if self._correction_service is None and self._get_correction_service:
            self._correction_service = self._get_correction_service()
        if not self._correction_service:
            return

        from app.components.widgets.commit_to_memory_prompt import CommitToMemoryPrompt

        source_text = self.segments[index].source_text if index < len(self.segments) else ""
        thematic_focus = ""
        if self._settings:
            thematic_focus = self._settings.get_thematic_focus()

        def on_yes():
            try:
                self._correction_service.commit_correction(
                    german_source=source_text,
                    original_translation=original_text,
                    corrected_translation=corrected_text,
                    thematic_focus=thematic_focus,
                )
                if self._bus:
                    self._bus.show_banner("Correction committed to memory")
            except Exception as exc:
                if self._bus:
                    self._bus.show_banner(f"Failed to commit correction: {exc}", is_error=True)

        def on_no():
            pass  # Correction saved locally in VersionStore only

        prompt = CommitToMemoryPrompt(page=self._page, on_yes=on_yes, on_no=on_no)
        prompt.show()

    def _on_compare(self, tab_id: int, segment_index: int):
        """Compute diff between active version and previous version, show DiffView overlay."""
        if not self._version_store:
            return

        from app.services.diff_computer import DiffComputer
        from app.components.views.diff_view import DiffView

        versions = self._version_store.get_versions(tab_id, segment_index)
        if len(versions) < 2:
            return

        active_idx = self._version_store._active.get(tab_id, {}).get(segment_index, 0)
        active_idx = max(0, min(active_idx, len(versions) - 1))

        # Compare active version with the one before it (or first if active is 0)
        prev_idx = max(0, active_idx - 1)
        if prev_idx == active_idx and active_idx + 1 < len(versions):
            prev_idx = active_idx + 1

        text_a = versions[prev_idx].text
        text_b = versions[active_idx].text

        diff_ops = DiffComputer.compute_diff(text_a, text_b)

        def on_accept():
            self._on_accept(tab_id, segment_index)
            self._close_diff_overlay(segment_index)

        def on_close():
            self._close_diff_overlay(segment_index)

        diff_view = DiffView(
            diff_ops=diff_ops,
            version_a_label=f"v{prev_idx + 1}",
            version_b_label=f"v{active_idx + 1}",
            on_accept=on_accept,
            on_close=on_close,
        )

        # Show diff overlay in the translation container
        self._diff_overlay_segment = segment_index
        container = self._translation_containers[segment_index]
        container.content = diff_view.build()
        try:
            container.update()
        except Exception:
            pass

    def _close_diff_overlay(self, segment_index: int):
        """Close the diff overlay and restore the segment display."""
        self._diff_overlay_segment = -1
        self._refresh_translation_segment(segment_index)

    def _on_accept(self, tab_id: int, segment_index: int):
        """Accept the current active version, update translation_tabs in AppState."""
        if not self._version_store:
            return

        active_version = self._version_store.get_active_version(tab_id, segment_index)
        if active_version:
            self._update_translation_tab_text(segment_index, active_version.text)
            self._refresh_translation_segment(segment_index)

    def _update_translation_tab_text(self, segment_index: int, new_text: str):
        """Update the translation text in AppState's translation_tabs for this segment."""
        # Rebuild the full translation from all active versions
        full_parts = []
        for i, seg in enumerate(self.segments):
            if i == segment_index:
                full_parts.append(new_text)
            elif self._version_store:
                active = self._version_store.get_active_version(self._tab_id, i)
                full_parts.append(active.text if active else seg.translation_text)
            else:
                full_parts.append(seg.translation_text)

        full_translation = "\n\n".join(full_parts)

        # Update the translation_data dict (which is a reference to the AppState entry)
        self.translation_data["translation"] = full_translation

    def _get_segment_translation_text(self, index: int) -> str:
        """Get the current translation text for a segment (from VersionStore or original)."""
        if self._version_store:
            active = self._version_store.get_active_version(self._tab_id, index)
            if active:
                return active.text
        if index < len(self.segments):
            return self.segments[index].translation_text
        return ""

    def _restore_translation_segment(self, index: int):
        """Restore a translation segment to its read-only display."""
        text = self._get_segment_translation_text(index)
        self._refresh_translation_segment(index)

    def _refresh_translation_segment(self, index: int):
        """Refresh a translation segment's display with current version text and HITL controls."""
        text = self._get_segment_translation_text(index)

        text_control = ft.Text(
            text,
            size=16,
            font_family=Fonts.SERIF,
            color=Colors.INK,
            selectable=True,
            style=ft.TextStyle(height=1.75),
        )

        content_controls: list[ft.Control] = []

        # Re-translate button
        retranslate_btn = ft.IconButton(
            icon=ft.Icons.REFRESH,
            icon_size=14,
            icon_color=Colors.INK_MUTED,
            tooltip="Re-translate this segment",
            on_click=lambda e, idx=index: self._on_retranslate_click(idx),
            style=ft.ButtonStyle(padding=ft.padding.all(0)),
            width=24,
            height=24,
        )
        header_row = ft.Row(
            controls=[ft.Container(expand=True), retranslate_btn],
            spacing=4,
            alignment=ft.MainAxisAlignment.END,
        )
        content_controls.append(header_row)
        content_controls.append(text_control)

        # VersionNav
        version_nav_row = self._build_version_nav(index)
        if version_nav_row:
            content_controls.append(version_nav_row)

        container = self._translation_containers[index]
        container.content = ft.Column(controls=content_controls, spacing=4)
        try:
            container.update()
        except Exception:
            pass

    def _build_missing_pdf_column(self, source_texts) -> ft.Column:
        """Build the left column with a red error banner + text fallback for a missing PDF."""
        basename = os.path.basename(self.pdf_path)

        banner = ft.Container(
            bgcolor=Colors.DESTRUCTIVE,
            border_radius=8,
            padding=ft.padding.all(16),
            content=ft.Column(
                controls=[
                    ft.Row(
                        controls=[
                            ft.Icon(ft.Icons.ERROR, color=Colors.DESTRUCTIVE_FOREGROUND, size=20),
                            ft.Text(
                                f"PDF not found: {basename}",
                                color=Colors.DESTRUCTIVE_FOREGROUND,
                                size=13,
                                weight=ft.FontWeight.W_600,
                            ),
                        ],
                        spacing=8,
                    ),
                    ft.Text(
                        self.pdf_path,
                        color=Colors.INK_MUTED,
                        size=11,
                        italic=True,
                    ),
                    ft.ElevatedButton(
                        content=ft.Text("Browse", font_family=Fonts.FRAKTUR, color=Colors.DESTRUCTIVE),
                        bgcolor=Colors.PRIMARY,
                        on_click=lambda _: self._file_picker.pick_files(
                            allowed_extensions=["pdf"],
                        ),
                    ),
                ],
                spacing=8,
            ),
        )

        text_col = self._build_column("Quelle · German", source_texts, "source")

        return ft.Column(
            controls=[banner, text_col],
            spacing=0,
            expand=True,
        )

    def _on_pdf_relocated(self, e: ft.FilePickerResultEvent):
        """Handle the result of the file picker for re-locating a missing PDF."""
        if not e.files:
            return
        selected = e.files[0].path
        if not selected or not selected.lower().endswith(".pdf") or not os.path.isfile(selected):
            return

        # Cleanup old PDF viewer if one exists
        if self._pdf_viewer is not None:
            self._pdf_viewer.cleanup()
            self._pdf_viewer = None

        self.pdf_path = selected
        self.translation_data["pdf_path"] = selected

        # Persist the updated path to history JSON
        history_mgr = self._actions.get("history_manager")
        timestamp = self.translation_data.get("history_timestamp")
        if history_mgr and timestamp:
            history_mgr.update_pdf_path(timestamp, selected)

        new_left = self._build_pdf_column()
        if self._parallel_row is not None:
            self._parallel_row.controls[0] = new_left
        if self._page is not None:
            self._page.update()

    def _build_column_header(self, label: str) -> ft.Container:
        """Build a sticky header for a source/translation column."""
        return ft.Container(
            content=ft.Text(
                label,
                size=13,
                color=Colors.INK_MUTED,
                italic=True,
                font_family=Fonts.SERIF,
            ),
            padding=ft.padding.symmetric(horizontal=24, vertical=8),
            bgcolor=Colors.SURFACE,
            border=ft.border.only(bottom=ft.BorderSide(1, Colors.DIVIDER)),
        )

    def _build_pdf_column(self) -> ft.Column:
        """Build the left column with an embedded PDF viewer instead of text segments."""
        from app.components.views.pdf_viewer import WebView_PDF_Viewer

        self._pdf_viewer = WebView_PDF_Viewer(self._page)
        self._pdf_viewer.load_pdf(self.pdf_path, os.path.basename(self.pdf_path))

        return ft.Column(
            controls=[
                self._build_column_header(f"Quelle · {os.path.basename(self.pdf_path)}"),
                ft.Container(
                    content=self._pdf_viewer.build(),
                    expand=True,
                ),
            ],
            spacing=0,
            expand=True,
        )

    def _build_column(self, header_label: str, texts, side: str) -> ft.Column:
        """Build one scrollable column (header + segments)."""
        segments = [
            self._build_segment(seg_text, i, side)
            for i, seg_text in enumerate(texts)
        ]

        inner_scroll_col = ft.ListView(
            controls=segments,
            spacing=0,
            on_scroll=self._on_source_scroll if side == "source" else self._on_translation_scroll,
            expand=True,
        )

        # Store reference for scroll_to support
        if side == "source":
            self._source_scroll_col = inner_scroll_col
        else:
            self._translation_scroll_col = inner_scroll_col

        return ft.Column(
            controls=[
                self._build_column_header(header_label),
                inner_scroll_col,
            ],
            spacing=0,
            expand=True,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def build(self) -> ft.Control:
        """Build the parallel view with two synchronized columns."""
        source_texts = [s.source_text for s in self.segments]
        translation_texts = [s.translation_text for s in self.segments]

        # Left side: three-way branch based on pdf_path state
        if self.pdf_path and os.path.isfile(self.pdf_path) and self._page:
            left_col = self._build_pdf_column()
        elif self.pdf_path and not os.path.isfile(self.pdf_path):
            left_col = self._build_missing_pdf_column(source_texts)
        else:
            left_col = self._build_column("Quelle · German", source_texts, "source")

        right_col = self._build_column("Übersetzung · English", translation_texts, "translation")

        # Vertical divider between the two columns
        divider = ft.VerticalDivider(width=1, color=Colors.DIVIDER)

        # The parallel row must expand to fill available space.
        parallel_row = ft.Row(
            controls=[left_col, divider, right_col],
            spacing=0,
            expand=True,
            vertical_alignment=ft.CrossAxisAlignment.STRETCH,
        )
        self._parallel_row = parallel_row

        # Main layout: parallel columns expand to fill, commentary + footer pinned below
        layout_controls: list[ft.Control] = [parallel_row]

        # Commentary goes below the parallel columns (not inside a scrollable wrapper)
        commentary_controls = self._build_commentary_section()
        if commentary_controls:
            layout_controls.append(
                ft.Container(
                    content=ft.Column(
                        controls=commentary_controls,
                        spacing=0,
                        scroll=ft.ScrollMode.AUTO,
                    ),
                    height=250,
                    bgcolor=Colors.BACKGROUND,
                )
            )

        if self.metrics_footer:
            layout_controls.append(self.metrics_footer)

        result = ft.Column(
            controls=layout_controls,
            spacing=0,
            expand=True,
        )
        self._built_tree = result
        return result

    def get_tab_title(self) -> str:
        """Return a short title suitable for the tab bar."""
        return self.translation_data.get("source_preview", "Translation")

    def get_source_text(self) -> str:
        """Return the full German source text."""
        return self.translation_data.get("source_full", "")

    @staticmethod
    def _scrub_flet_control(ctrl):
        """Recursively clear Flet's internal event handler storage on a control tree."""
        if ctrl is None:
            return
        for attr in ('_Control__event_handlers', '_event_handlers', '__event_handlers'):
            d = getattr(ctrl, attr, None)
            if isinstance(d, dict):
                d.clear()
        # Clear Flet's internal attrs dict (property-backed values)
        for attr in ('_Control__attrs', '_attrs'):
            d = getattr(ctrl, attr, None)
            if isinstance(d, dict):
                for k in [k for k in d if k.startswith('on')]:
                    d.pop(k, None)
        for attr in dir(ctrl):
            if attr.startswith('on_') and callable(getattr(ctrl, attr, None)):
                try:
                    setattr(ctrl, attr, None)
                except Exception:
                    pass
        if hasattr(ctrl, 'content') and ctrl.content is not None:
            ParallelView._scrub_flet_control(ctrl.content)
            try:
                ctrl.content = None
            except Exception:
                pass
        if hasattr(ctrl, 'controls') and isinstance(ctrl.controls, list):
            for child in list(ctrl.controls):
                ParallelView._scrub_flet_control(child)
            try:
                ctrl.controls.clear()
            except Exception:
                pass

    def cleanup(self):
        """Release resources to prevent memory leaks on tab close/switch."""
        import gc
        from app.mem_debug import log_mem
        log_mem("ParallelView.cleanup START")

        # Recursively scrub all Flet event handlers from the built control tree
        if self._built_tree is not None:
            ParallelView._scrub_flet_control(self._built_tree)
            self._built_tree = None

        # Scrub segment containers (hold _on_compare/_on_accept closures)
        for c in self._source_containers:
            ParallelView._scrub_flet_control(c)
        for c in self._translation_containers:
            ParallelView._scrub_flet_control(c)

        # Scrub scroll columns
        if self._source_scroll_col is not None:
            ParallelView._scrub_flet_control(self._source_scroll_col)
        if self._translation_scroll_col is not None:
            ParallelView._scrub_flet_control(self._translation_scroll_col)

        # Cleanup PDF viewer
        if self._pdf_viewer is not None:
            self._pdf_viewer.cleanup()
            self._pdf_viewer = None

        # Remove the FilePicker from page.overlay
        if self._page is not None and self._file_picker is not None:
            try:
                self._file_picker.on_result = None
                self._page.overlay.remove(self._file_picker)
            except (ValueError, Exception):
                pass
            self._file_picker = None

        # Fallback: iterate overlay to remove any stale FilePicker whose
        # on_result is a bound method on this instance (handles cases where
        # self._file_picker was already removed or replaced).
        if self._page is not None:
            try:
                stale_pickers = []
                for ctrl in self._page.overlay:
                    if isinstance(ctrl, ft.FilePicker):
                        handler = getattr(ctrl, "on_result", None)
                        if handler is not None and getattr(handler, "__self__", None) is self:
                            stale_pickers.append(ctrl)
                for picker in stale_pickers:
                    picker.on_result = None
                    try:
                        self._page.overlay.remove(picker)
                    except (ValueError, Exception):
                        pass
            except Exception:
                pass

        # Remove stale AlertDialogs from overlay
        if self._page is not None:
            try:
                import flet as ft
                self._page.overlay[:] = [
                    c for c in self._page.overlay
                    if not isinstance(c, ft.AlertDialog)
                ]
            except Exception:
                pass

        # Drop all data references
        self._source_containers.clear()
        self._translation_containers.clear()
        self._source_scroll_col = None
        self._translation_scroll_col = None
        if self._parallel_row is not None:
            ParallelView._scrub_flet_control(self._parallel_row)
        self._parallel_row = None
        self.segments = []
        self.translation_data = {}
        self.commentary = None
        self.metrics = None
        if self.metrics_footer is not None:
            ParallelView._scrub_flet_control(self.metrics_footer)
        self.metrics_footer = None
        self._version_nav_rows.clear()
        self._diff_overlay = None

        # Break references to services/actions
        self._version_store = None
        self._re_translation_engine = None
        self._correction_service = None
        self._get_correction_service = None
        self._bus = None
        self._settings = None
        self._actions = {}

        # Drop page reference last
        self._page = None

        gc.collect()
        log_mem("ParallelView.cleanup END")
