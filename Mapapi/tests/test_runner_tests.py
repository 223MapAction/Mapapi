from django.test import TestCase
from unittest.mock import patch, MagicMock
from Mapapi.test_runner import CoverageRunner


class TestCoverageRunner(TestCase):
    """Tests for the CoverageRunner class"""

    @patch('coverage.Coverage')
    def test_init(self, mock_coverage):
        """Test initialization of CoverageRunner"""
        runner = CoverageRunner()
        mock_coverage.assert_called_once_with(
            source=['Mapapi'],
            omit=['*/tests/*', '*/migrations/*'],
            data_file='/app/coverage/.coverage',
        )

    @patch('coverage.Coverage')
    def test_run_tests(self, mock_coverage):
        """Test run_tests method of CoverageRunner"""
        mock_coverage_instance = MagicMock()
        mock_coverage.return_value = mock_coverage_instance

        # Mock the parent class's run_tests method
        with patch.object(CoverageRunner, '__init__', return_value=None):
            with patch('django.test.runner.DiscoverRunner.run_tests', return_value=42):
                runner = CoverageRunner()
                runner.coverage = mock_coverage_instance
                result = runner.run_tests(['test_label'])

        # Verify all the coverage methods were called
        mock_coverage_instance.start.assert_called_once()
        mock_coverage_instance.stop.assert_called_once()
        mock_coverage_instance.save.assert_called_once()
        mock_coverage_instance.xml_report.assert_called_once_with(outfile='/app/coverage/coverage.xml')
        
        # Verify the result is passed through
        self.assertEqual(result, 42)
