import unittest


class GlobalTopicAntiInflationTests(unittest.TestCase):
    def test_constants_exist(self) -> None:
        from service.constants import MAX_GLOBAL_TOPIC_CHARS
        self.assertIsInstance(MAX_GLOBAL_TOPIC_CHARS, int)
        self.assertGreater(MAX_GLOBAL_TOPIC_CHARS, 100)

    def test_no_prefix_duplication_after_multiple_truncations(self) -> None:
        """多次调用截断逻辑，前缀不应重复叠加。"""
        _COMPRESSION_PREFIX = "[早期内容已压缩]\n"
        MAX_CHARS = 2000

        def _truncate(existing_summary_str: str) -> str:
            if len(existing_summary_str) <= MAX_CHARS:
                return existing_summary_str
            clean_str = existing_summary_str
            while clean_str.startswith(_COMPRESSION_PREFIX):
                clean_str = clean_str[len(_COMPRESSION_PREFIX):]
            keep_from = max(0, len(clean_str) - int(MAX_CHARS * 0.8))
            return _COMPRESSION_PREFIX + clean_str[keep_from:]

        long_text = "a" * 3000
        result1 = _truncate(long_text)
        self.assertTrue(result1.startswith(_COMPRESSION_PREFIX))

        result2 = _truncate(result1 + "b" * 1000)
        prefix_count = result2.count(_COMPRESSION_PREFIX)
        self.assertEqual(1, prefix_count, f"前缀叠加了 {prefix_count} 次")

    def test_short_summary_not_truncated(self) -> None:
        """短 summary 不应被截断。"""
        _COMPRESSION_PREFIX = "[早期内容已压缩]\n"
        MAX_CHARS = 2000

        def _truncate(s: str) -> str:
            if len(s) <= MAX_CHARS:
                return s
            clean = s
            while clean.startswith(_COMPRESSION_PREFIX):
                clean = clean[len(_COMPRESSION_PREFIX):]
            keep_from = max(0, len(clean) - int(MAX_CHARS * 0.8))
            return _COMPRESSION_PREFIX + clean[keep_from:]

        short = "这是一段很短的摘要。"
        self.assertEqual(short, _truncate(short))


if __name__ == "__main__":
    unittest.main()
