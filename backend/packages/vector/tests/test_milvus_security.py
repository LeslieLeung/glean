"""Test security aspects of Milvus client."""

from glean_vector.clients.milvus_client import MilvusClient


class TestMilvusClientSecurity:
    """Test security-related functionality of MilvusClient."""

    def test_escape_string_basic(self) -> None:
        """Test basic string escaping."""
        assert MilvusClient._escape_string("normal_id") == "normal_id"
        assert MilvusClient._escape_string("id-with-dash") == "id-with-dash"
        assert MilvusClient._escape_string("id_with_underscore") == "id_with_underscore"

    def test_escape_string_quotes(self) -> None:
        """Test escaping of double quotes."""
        # Single quote should be escaped
        assert MilvusClient._escape_string('id"with"quotes') == 'id\\"with\\"quotes'

        # Multiple quotes
        assert MilvusClient._escape_string('""""""') == '\\"\\"\\"\\"\\"\\"'

    def test_escape_string_backslashes(self) -> None:
        """Test escaping of backslashes."""
        # Single backslash should be doubled
        assert MilvusClient._escape_string("id\\with\\backslash") == "id\\\\with\\\\backslash"

        # Multiple backslashes
        assert MilvusClient._escape_string("\\\\\\\\") == "\\\\\\\\\\\\\\\\"

    def test_escape_string_mixed(self) -> None:
        """Test escaping of mixed special characters."""
        # Backslash followed by quote
        assert MilvusClient._escape_string('id\\"test') == 'id\\\\\\"test'

        # Quote followed by backslash
        assert MilvusClient._escape_string('id"\\test') == 'id\\"\\\\test'

    def test_escape_string_injection_attempts(self) -> None:
        """Test prevention of injection attempts."""
        # Attempt to break out of quotes
        injection_id = 'malicious" OR 1==1 OR id=="'
        escaped = MilvusClient._escape_string(injection_id)
        assert '"' not in escaped.replace('\\"', "")  # No unescaped quotes

        # Attempt with backslash escape
        injection_id2 = 'malicious\\" OR 1==1 OR id==\\"'
        escaped2 = MilvusClient._escape_string(injection_id2)
        # Should not allow breaking out of the string
        assert escaped2 == 'malicious\\\\\\" OR 1==1 OR id==\\\\\\"'

    def test_filter_expression_safety(self) -> None:
        """Test that filter expressions are safe after escaping."""
        # Simulate what would happen in actual code
        malicious_id = 'test" OR 1==1 OR id=="bad'
        escaped_id = MilvusClient._escape_string(malicious_id)
        expr = f'id == "{escaped_id}"'

        # The expression should be a single equality check, not a complex OR expression
        # After escaping, the quotes in the malicious string are escaped
        assert expr == 'id == "test\\" OR 1==1 OR id==\\"bad"'
        # This is safe because the escaped quotes won't break the string boundary

    def test_batch_query_safety(self) -> None:
        """Test that batch queries are safe after escaping."""
        entry_ids = ["normal_id", 'id"with"quotes', "id\\with\\backslash"]

        # Simulate what happens in batch_get_entry_embeddings
        ids_str = ", ".join(f'"{MilvusClient._escape_string(eid)}"' for eid in entry_ids)
        expr = f"id in [{ids_str}]"

        expected = 'id in ["normal_id", "id\\"with\\"quotes", "id\\\\with\\\\backslash"]'
        assert expr == expected
