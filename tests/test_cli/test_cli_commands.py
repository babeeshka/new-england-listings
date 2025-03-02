# tests/test_cli/test_cli_commands.py
import pytest
import os
import json
import sys
import tempfile
import asyncio
from pathlib import Path
from unittest.mock import patch, MagicMock, AsyncMock

from new_england_listings.cli import (
    parse_args,
    async_main,
    main,
    process_urls,
    serialize_result,
    serialize_value
)


@pytest.fixture
def temp_output_file():
    """Create a temporary file for testing output."""
    fd, path = tempfile.mkstemp()
    yield path
    os.close(fd)
    os.unlink(path)


@pytest.fixture
def mock_process_listing():
    """Mock the process_listing function."""
    with patch('new_england_listings.cli.process_listing') as mock:
        # Configure mock to return test data
        async def mock_process(url, **kwargs):
            return {
                "listing_name": f"Mock Listing for {url}",
                "location": "Portland, ME",
                "price": "$500,000",
                "price_bucket": "$300K - $600K",
                "url": url,
                "platform": "Test Platform"
            }

        mock.side_effect = mock_process
        yield mock


class TestArgumentParsing:
    """Tests for the CLI argument parsing."""

    def test_parse_args_listings_command(self):
        """Test parsing listings command with URLs."""
        args = parse_args(["listings", "https://example.com/1",
                          "https://example.com/2", "--no-notion"])

        assert args.command == "listings"
        assert args.urls == ["https://example.com/1", "https://example.com/2"]
        assert args.no_notion is True

    def test_parse_args_authenticate_command(self):
        """Test parsing authenticate command."""
        args = parse_args(
            ["authenticate", "--url", "https://www.zillow.com/custom"])

        assert args.command == "authenticate"
        assert args.url == "https://www.zillow.com/custom"

    def test_parse_args_records_command(self):
        """Test parsing records command."""
        args = parse_args(
            ["records", "123 Main St, Portland, ME", "--county", "Cumberland"])

        assert args.command == "records"
        assert args.address == "123 Main St, Portland, ME"
        assert args.county == "Cumberland"

    def test_parse_args_global_options(self):
        """Test parsing global options."""
        args = parse_args(["listings", "https://example.com",
                          "--verbose", "--log-dir", "custom_logs"])

        assert args.verbose is True
        assert args.log_dir == "custom_logs"

    def test_parse_args_legacy_handling(self):
        """Test backward compatibility for arguments without command."""
        with patch('sys.argv', ["script.py", "https://example.com", "--no-notion"]):
            args = parse_args()

            assert args.command == "listings"
            assert args.urls == ["https://example.com"]
            assert args.no_notion is True


class TestProcessUrls:
    """Tests for the process_urls function."""

    @pytest.mark.asyncio
    async def test_process_urls_success(self, mock_process_listing):
        """Test processing multiple URLs successfully."""
        urls = ["https://example.com/1", "https://example.com/2"]

        result = await process_urls(urls, use_notion=False, verbose=True)

        # Verify result structure
        assert "results" in result
        assert "errors" in result
        assert "total" in result
        assert "successful" in result
        assert "failed" in result

        # Verify counts
        assert result["total"] == 2
        assert result["successful"] == 2
        assert result["failed"] == 0

        # Verify results contain expected data
        assert len(result["results"]) == 2
        assert result["results"][0]["listing_name"] == f"Mock Listing for {urls[0]}"
        assert result["results"][1]["listing_name"] == f"Mock Listing for {urls[1]}"

        # Verify mock was called correctly
        assert mock_process_listing.call_count == 2

    @pytest.mark.asyncio
    async def test_process_urls_with_errors(self, mock_process_listing):
        """Test processing URLs with some errors."""
        # Configure mock to fail for the second URL
        url_results = {
            "https://example.com/1": {"listing_name": "Success", "url": "https://example.com/1"},
            "https://example.com/2": Exception("Test error")
        }

        async def side_effect(url, **kwargs):
            result = url_results[url]
            if isinstance(result, Exception):
                raise result
            return result

        mock_process_listing.side_effect = side_effect

        urls = ["https://example.com/1", "https://example.com/2"]
        result = await process_urls(urls, use_notion=False)

        # Verify counts
        assert result["total"] == 2
        assert result["successful"] == 1
        assert result["failed"] == 1

        # Verify error was recorded
        assert len(result["errors"]) == 1
        assert "https://example.com/2" in result["errors"][0]["url"]
        assert "Test error" in result["errors"][0]["error"]

    @pytest.mark.asyncio
    async def test_process_urls_output_to_file(self, mock_process_listing, temp_output_file):
        """Test writing process results to output file."""
        urls = ["https://example.com/test"]

        # Use a real file for testing
        await process_urls(urls, use_notion=False, output_file=temp_output_file)

        # Verify file was created and contains valid JSON
        assert os.path.exists(temp_output_file)
        with open(temp_output_file, 'r') as f:
            data = json.load(f)
            assert "results" in data
            assert len(data["results"]) == 1


class TestSerializationFunctions:
    """Tests for the serialization functions."""

    def test_serialize_value_primitives(self):
        """Test serializing primitive values."""
        assert serialize_value("test") == "test"
        assert serialize_value(123) == 123
        assert serialize_value(10.5) == 10.5
        assert serialize_value(True) is True
        assert serialize_value(None) is None

    def test_serialize_value_datetime(self):
        """Test serializing datetime objects."""
        from datetime import datetime, date

        # Test datetime
        dt = datetime(2023, 1, 15, 12, 30, 0)
        assert serialize_value(dt) == "2023-01-15T12:30:00"

        # Test date
        d = date(2023, 1, 15)
        assert serialize_value(d) == "2023-01-15"

    def test_serialize_value_collections(self):
        """Test serializing collections."""
        # Test list
        assert serialize_value([1, "test", None]) == [1, "test", None]

        # Test dict
        assert serialize_value({"key": "value", "num": 123}) == {
            "key": "value", "num": 123}

        # Test nested structures
        nested = {
            "list": [1, 2, {"nested": True}],
            "dict": {"inner": [3, 4]}
        }
        serialized = serialize_value(nested)
        assert serialized["list"][2]["nested"] is True
        assert serialized["dict"]["inner"] == [3, 4]

    def test_serialize_value_custom_objects(self):
        """Test serializing custom objects."""
        class TestClass:
            def __init__(self):
                self.name = "test"
                self.value = 123

        obj = TestClass()
        serialized = serialize_value(obj)
        assert isinstance(serialized, dict)
        assert serialized["name"] == "test"
        assert serialized["value"] == 123


@pytest.mark.asyncio
class TestMainFunction:
    """Tests for the main entry point functions."""

    @patch('new_england_listings.cli.setup_logging')
    @patch('new_england_listings.cli.process_urls')
    async def test_async_main_listings_command(self, mock_process_urls, mock_setup_logging):
        """Test async_main with listings command."""
        # Configure process_urls mock
        mock_process_urls.return_value = {
            "results": [{"listing_name": "Test"}],
            "errors": [],
            "total": 1,
            "successful": 1,
            "failed": 0
        }

        # Mock the args
        mock_args = MagicMock()
        mock_args.command = "listings"
        mock_args.urls = ["https://example.com/test"]
        mock_args.no_notion = False
        mock_args.output = None
        mock_args.verbose = False

        with patch('new_england_listings.cli.parse_args', return_value=mock_args):
            # Call async_main
            await async_main()

            # Verify process_urls was called correctly
            mock_process_urls.assert_called_once_with(
                ["https://example.com/test"],
                use_notion=True,
                verbose=False
            )

            # Verify logging was set up
            mock_setup_logging.assert_called_once()

    @patch('new_england_listings.cli.setup_logging')
    @patch('builtins.print')
    async def test_async_main_authenticate_command(self, mock_print, mock_setup_logging):
        """Test async_main with authenticate command."""
        # Mock the browser_auth module
        with patch('new_england_listings.cli.get_zillow_with_user_consent') as mock_auth:
            mock_auth.return_value = True  # Successful authentication

            # Mock the args
            mock_args = MagicMock()
            mock_args.command = "authenticate"
            mock_args.url = "https://www.zillow.com/"
            mock_args.verbose = False

            with patch('new_england_listings.cli.parse_args', return_value=mock_args):
                # Call async_main
                await async_main()

                # Verify authentication was called
                mock_auth.assert_called_once_with("https://www.zillow.com/")

                # Verify success message was printed
                success_call = False
                for call_args in mock_print.call_args_list:
                    args, _ = call_args
                    if any("successful" in str(arg).lower() for arg in args):
                        success_call = True
                        break
                assert success_call

    @patch('new_england_listings.cli.setup_logging')
    @patch('builtins.print')
    async def test_async_main_records_command(self, mock_print, mock_setup_logging):
        """Test async_main with records command."""
        # Mock the property_records module
        with patch('new_england_listings.cli.MainePropertyRecords') as MockRecords:
            instance = MockRecords.return_value
            instance.search_by_address.return_value = {
                "source": "Test County Records",
                "address": "123 Main St, Portland, ME",
                "record_url": "https://example.com/records/123"
            }

            # Mock the args
            mock_args = MagicMock()
            mock_args.command = "records"
            mock_args.address = "123 Main St, Portland, ME"
            mock_args.county = None
            mock_args.verbose = False

            with patch('new_england_listings.cli.parse_args', return_value=mock_args):
                # Call async_main
                await async_main()

                # Verify search_by_address was called correctly
                instance.search_by_address.assert_called_once_with(
                    "123 Main St", "Portland", "ME"
                )

                # Verify results were printed
                found_call = False
                for call_args in mock_print.call_args_list:
                    args, _ = call_args
                    if any("found property records" in str(arg).lower() for arg in args):
                        found_call = True
                        break
                assert found_call

    @patch('new_england_listings.cli.asyncio.run')
    def test_main_function(self, mock_asyncio_run):
        """Test the synchronous main entry point."""
        # Call main
        main(["listings", "https://example.com/test"])

        # Verify asyncio.run was called
        mock_asyncio_run.assert_called_once()

        # For Windows platform testing
        with patch('sys.platform', 'win32'):
            with patch('asyncio.set_event_loop_policy') as mock_set_policy:
                main(["listings", "https://example.com/test"])
                mock_set_policy.assert_called_once()

    @patch('sys.exit')
    @patch('new_england_listings.cli.asyncio.run')
    def test_main_with_keyboard_interrupt(self, mock_asyncio_run, mock_exit):
        """Test handling of KeyboardInterrupt."""
        # Configure asyncio.run to raise KeyboardInterrupt
        mock_asyncio_run.side_effect = KeyboardInterrupt()

        # Call main
        main(["listings", "https://example.com/test"])

        # Verify sys.exit was called with code 130
        mock_exit.assert_called_once_with(130)

    @patch('sys.exit')
    @patch('new_england_listings.cli.asyncio.run')
    def test_main_with_error(self, mock_asyncio_run, mock_exit):
        """Test handling of general errors."""
        # Configure asyncio.run to raise Exception
        mock_asyncio_run.side_effect = Exception("Test error")

        # Call main
        main(["listings", "https://example.com/test"])

        # Verify sys.exit was called with code 1
        mock_exit.assert_called_once_with(1)


# Use this conditional to enable running the tests directly
if __name__ == "__main__":
    pytest.main(["-xvs", __file__])
