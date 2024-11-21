import unittest
from unittest.mock import patch, MagicMock
from Send_mails import send_email
import logging

class SendEmailTests(unittest.TestCase):
    
    @patch("Send_mails.render_to_string")
    @patch("Send_mails.EmailMultiAlternatives")
    @patch("Send_mails.logger")
    def test_send_email_success(self, mock_logger, MockEmailMultiAlternatives, mock_render_to_string):
        # Thiết lập dữ liệu
        subject = "Chủ đề kiểm tra"
        template_name = "test_template.html"
        context = {"name": "Test"}
        to_email = "test@example.com"
        mock_render_to_string.return_value = "<p>Hello, Test</p>"
        
        mock_email_instance = MockEmailMultiAlternatives.return_value
        mock_email_instance.send.return_value = True
        
        # Thực hiện hành động
        send_email(subject, template_name, context, to_email)
        
        # Xác minh kết quả
        mock_render_to_string.assert_called_once_with(template_name, context)
        MockEmailMultiAlternatives.assert_called_once_with(
            subject, 
            "Hello, Test",  # Nội dung văn bản thuần dự kiến
            'Map Action <contact@map-action.com>',
            [to_email]
        )
        mock_email_instance.attach_alternative.assert_called_once_with("<p>Hello, Test</p>", "text/html")
        mock_email_instance.send.assert_called_once()
        
        # Kiểm tra log cho trường hợp thành công
        mock_logger.info.assert_any_call(f"Début de l'envoi de l'email à {to_email} avec le sujet {subject}.")
        mock_logger.info.assert_any_call(f"Email envoyé avec succès à {to_email}.")

    @patch("Send_mails.render_to_string")
    @patch("Send_mails.EmailMultiAlternatives")
    @patch("Send_mails.logger")
    def test_send_email_failure(self, mock_logger, MockEmailMultiAlternatives, mock_render_to_string):
        # Thiết lập dữ liệu
        subject = "Chủ đề kiểm tra"
        template_name = "test_template.html"
        context = {"name": "Test"}
        to_email = "test@example.com"
        mock_render_to_string.return_value = "<p>Hello, Test</p>"
        
        mock_email_instance = MockEmailMultiAlternatives.return_value
        mock_email_instance.send.side_effect = Exception("SMTP error")
        
        # Thực hiện hành động và kiểm tra ngoại lệ
        with self.assertRaises(Exception) as context:
            send_email(subject, template_name, context, to_email)
        
        # Xác minh kết quả
        mock_render_to_string.assert_called_once_with(template_name, context)
        MockEmailMultiAlternatives.assert_called_once_with(
            subject, 
            "Hello, Test", 
            'Map Action <contact@map-action.com>',
            [to_email]
        )
        mock_email_instance.attach_alternative.assert_called_once_with("<p>Hello, Test</p>", "text/html")
        mock_email_instance.send.assert_called_once()
        
        # Kiểm tra log cho trường hợp lỗi
        mock_logger.info.assert_any_call(f"Début de l'envoi de l'email à {to_email} avec le sujet {subject}.")
        mock_logger.error.assert_called_once_with(f"Erreur lors de l'envoi de l'email: SMTP error")

if __name__ == "__main__":
    unittest.main()
