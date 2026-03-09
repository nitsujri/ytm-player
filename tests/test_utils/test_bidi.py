"""Tests for BiDi word-level reordering (bidi.py).

The reordering produces text that reads correctly when placed
left-to-right in a terminal without native BiDi support.  Arabic/Hebrew
readers scan right-to-left, so the rightmost word in LTR placement
is the first word in reading order.

Verification strategy: after reordering, the rightmost word(s) should
be the start of the sentence in RTL reading order.
"""

from ytm_player.utils.bidi import has_rtl, reorder_rtl_line, wrap_rtl_line

# ── has_rtl ──────────────────────────────────────────────────────────


class TestHasRtl:
    def test_pure_english(self):
        assert has_rtl("Hello World") is False

    def test_pure_arabic(self):
        assert has_rtl("مرحبا بالعالم") is True

    def test_pure_hebrew(self):
        assert has_rtl("שלום עולם") is True

    def test_mixed_arabic_english(self):
        assert has_rtl("Hello عالم") is True

    def test_empty_string(self):
        assert has_rtl("") is False

    def test_numbers_only(self):
        assert has_rtl("12345") is False

    def test_arabic_presentation_forms(self):
        # U+FE70 = Arabic Presentation Form-B
        assert has_rtl("\ufe70") is True

    def test_emoji_no_rtl(self):
        assert has_rtl("\U0001f3b5 Music") is False


# ── reorder_rtl_line — passthrough cases ─────────────────────────────


class TestReorderPassthrough:
    def test_empty_string(self):
        assert reorder_rtl_line("") == ""

    def test_whitespace_only(self):
        assert reorder_rtl_line("   ") == "   "

    def test_pure_english(self):
        assert reorder_rtl_line("Hello World") == "Hello World"

    def test_single_arabic_word(self):
        # One word — nothing to reorder.
        assert reorder_rtl_line("مرحبا") == "مرحبا"


# ── reorder_rtl_line — pure RTL ──────────────────────────────────────


class TestReorderPureRtl:
    def test_two_arabic_words_reversed(self):
        # "eyes heart" → reversed word order for LTR terminal
        result = reorder_rtl_line("عيون القلب")
        assert result == "القلب عيون"

    def test_four_arabic_words(self):
        result = reorder_rtl_line("يا ليل يا عين")
        assert result == "عين يا ليل يا"

    def test_arabic_with_tashkeel(self):
        # Diacritics should not affect direction detection.
        result = reorder_rtl_line("بِسْمِ اللَّهِ")
        assert result == "اللَّهِ بِسْمِ"

    def test_hebrew(self):
        result = reorder_rtl_line("שלום עולם")
        assert result == "עולם שלום"


# ── reorder_rtl_line — mixed RTL + LTR ───────────────────────────────


class TestReorderMixed:
    def test_rtl_base_with_english_suffix(self):
        # RTL base (first strong char is Arabic).
        # Arabic word stays rightmost; English goes left.
        result = reorder_rtl_line("حبيبي (Remix)")
        assert result == "(Remix) حبيبي"

    def test_ltr_base_with_arabic_suffix(self):
        # LTR base (first strong char is 'B').
        # "Beautiful Day -" stays in LTR order; Arabic part reverses internally.
        result = reorder_rtl_line("Beautiful Day - محمد حماقي")
        assert result == "Beautiful Day - حماقي محمد"

    def test_rtl_base_with_embedded_english(self):
        # LTR words embedded in RTL paragraph keep their internal order.
        result = reorder_rtl_line("كلمات DJ Khaled أغنية")
        assert result == "أغنية DJ Khaled كلمات"

    def test_rtl_base_feat(self):
        result = reorder_rtl_line("فيروز feat. Rahbani")
        assert result == "feat. Rahbani فيروز"

    def test_rtl_with_number(self):
        # Numbers are neutral; in RTL paragraph they get base level 1.
        result = reorder_rtl_line("أغنية رقم 3")
        assert result == "3 رقم أغنية"

    def test_rtl_with_dash(self):
        # Dash is neutral; inherits paragraph direction.
        result = reorder_rtl_line("عمرو دياب - تملي معاك")
        assert result == "معاك تملي - دياب عمرو"

    def test_ltr_base_keeps_ltr_order(self):
        # English text with Arabic in the middle.
        result = reorder_rtl_line("Song by فنان العرب is great")
        # LTR base: LTR stays, only the Arabic run reverses (2 words → swapped).
        assert result == "Song by العرب فنان is great"

    def test_multiple_ltr_blocks_in_rtl(self):
        result = reorder_rtl_line("كلمة Hello كلمة World كلمة")
        # RTL base: RTL words reverse, each LTR block keeps internal order.
        # levels: R=1 L=2 R=1 L=2 R=1
        # L2 at level 2: reverse [Hello] and [World] (each is solo, no change)
        # L2 at level 1: reverse entire sequence
        assert result == "كلمة World كلمة Hello كلمة"


# ── reorder_rtl_line — edge cases ────────────────────────────────────


class TestReorderEdgeCases:
    def test_arabic_with_parentheses(self):
        result = reorder_rtl_line("أنشودة (رائعة)")
        assert result == "(رائعة) أنشودة"

    def test_emoji_with_arabic(self):
        result = reorder_rtl_line("🎵 أغنية جميلة")
        # Emoji is neutral → base level (RTL), reversed with the rest.
        assert result == "جميلة أغنية 🎵"

    def test_arabic_comma(self):
        result = reorder_rtl_line("أحمد، محمد")
        assert result == "محمد أحمد،"

    def test_arabic_question_mark(self):
        result = reorder_rtl_line("ما هذا؟")
        assert result == "هذا؟ ما"


# ── wrap_rtl_line ────────────────────────────────────────────────────


class TestWrapRtlLine:
    def test_passthrough_ltr(self):
        assert wrap_rtl_line("Hello World", 80) == "Hello World"

    def test_passthrough_empty(self):
        assert wrap_rtl_line("", 80) == ""

    def test_short_rtl_no_wrap(self):
        text = "يا عين"
        result = wrap_rtl_line(text, 80)
        # Short text, no wrapping needed — just reorder.
        assert result == reorder_rtl_line(text)

    def test_wrap_splits_into_lines(self):
        text = "يا ليل يا عين ويا سهرني وطولت ليلي"
        result = wrap_rtl_line(text, 30)
        lines = result.split("\n")
        assert len(lines) == 2
        # Each line should be independently reordered.
        for line in lines:
            assert len(line) <= 30 or len(line.split()) == 1

    def test_wrap_each_line_reordered(self):
        text = "أنا أحب البرمجة كثيرا"
        result = wrap_rtl_line(text, 15)
        lines = result.split("\n")
        assert len(lines) == 2
        # Line 0 wraps "أنا أحب البرمجة" → reordered "البرمجة أحب أنا"
        assert lines[0] == "البرمجة أحب أنا"
        # Line 1 is the overflow word (single word, identity).
        assert lines[1] == "كثيرا"

    def test_wrap_zero_width_reorders(self):
        text = "يا عين"
        result = wrap_rtl_line(text, 0)
        assert result == reorder_rtl_line(text)

    def test_wrap_negative_width_reorders(self):
        text = "يا عين"
        result = wrap_rtl_line(text, -5)
        assert result == reorder_rtl_line(text)
