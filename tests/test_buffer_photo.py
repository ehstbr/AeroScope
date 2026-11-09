import unittest
from unittest.mock import patch
from aeroscope.data import fetch_photo_details, _parse_planespotters_response, PHOTO_IMAGE_HOSTS, _photo_url, download_thumbnail, _photo_json_get
from aeroscope.geoview import coverage_for_view, viewport_inside_radius, distance_nm

class BufferAndPhotoTests(unittest.TestCase):
    def test_center_is_covered(self):
        view = coverage_for_view(-20.14, -44.89, 10, 850, 650, max_queries=1)
        self.assertTrue(viewport_inside_radius(view, (-20.14, -44.89)))
    def test_pan_inside_250_nm(self):
        view = coverage_for_view(-20.14, -44.59, 10, 850, 650, max_queries=1)
        self.assertTrue(viewport_inside_radius(view, (-20.14, -44.89)))
    def test_pan_outside_250_nm(self):
        view = coverage_for_view(-20.14, -38.89, 10, 850, 650, max_queries=1)
        self.assertFalse(viewport_inside_radius(view, (-20.14, -44.89)))
    def test_zoom_out_larger_than_circle(self):
        view = coverage_for_view(-20.14, -44.89, 3, 1000, 650, max_queries=1)
        self.assertFalse(viewport_inside_radius(view, (-20.14, -44.89)))
    def test_photo_cdn_short_domain(self):
        self.assertIn('cdn.plnspttrs.net', PHOTO_IMAGE_HOSTS)
        result = _parse_planespotters_response({'photos':[{'thumbnail':{'src':'https://cdn.plnspttrs.net/test.jpg'},'link':'https://www.planespotters.net/photo/123','photographer':'Maria'}]})
        self.assertEqual(result['photographer'],'Maria')
    def test_photo_insecure_url_rejected(self):
        result = _parse_planespotters_response({'photos':[{'thumbnail':{'src':'http://cdn.plnspttrs.net/test.jpg'}}]})
        self.assertIsNone(result)
    @patch('aeroscope.data._photo_json_get')
    def test_photo_fallback_registration(self, read):
        read.side_effect=[{'photos':[]}, {'photos':[{'thumbnail':{'src':'https://cdn.plnspttrs.net/thumb.jpg'},'link':'https://www.planespotters.net/'}]}]
        self.assertIsNotNone(fetch_photo_details('ABC123','PR-XYZ'))
        self.assertTrue(read.call_args.args[0].endswith('/reg/PR-XYZ'))
    @patch('aeroscope.data._photo_json_get')
    def test_no_photo_returns_none(self, read):
        read.return_value={'photos':[]}
        self.assertIsNone(fetch_photo_details('ABC123', 'PR-XYZ'))

    def test_subdomain_and_protocol_relative_thumbnail(self):
        self.assertEqual(_photo_url('//cdn4.plnspttrs.net/aviation/photo.jpg'),
                         'https://cdn4.plnspttrs.net/aviation/photo.jpg')
        self.assertIsNone(_photo_url('https://cdn.plnspttrs.net.evil.com/x.jpg'))
        self.assertIsNone(_photo_url('https://cdn.plnspttrs.net:4443/x.jpg'))
        self.assertIsNone(_photo_url('http://cdn.plnspttrs.net/x.jpg'))

    def test_photo_log_fallback_and_credit(self):
        response = {'photos': [{'thumbnail': {'src': 'https://cdn.plnspttrs.net/a.jpg'},
                                'link': 'https://www.planespotters.net/photo/100', 'photographer':'Ana'}]}
        with patch('aeroscope.data._photo_json_get', side_effect=[{'photos': []}, response]) as mocked:
            with self.assertLogs('aeroscope.photos', 'INFO') as log:
                result = fetch_photo_details('ABC123', 'PR-XYZ')
        self.assertEqual(result['photographer'], 'Ana')
        self.assertEqual(mocked.call_count, 2)
        self.assertIn('matrícula', '\n'.join(log.output))

    def test_api_403_is_not_mistaken_for_missing_photo(self):
        with patch('aeroscope.data._photo_json_get', side_effect=RuntimeError('HTTP 403')):
            with self.assertLogs('aeroscope.photos', 'WARNING') as log:
                with self.assertRaisesRegex(RuntimeError, 'HTTP 403'):
                    fetch_photo_details('ABC123', 'PR-XYZ')
        self.assertIn('HTTP 403', '\n'.join(log.output))

    def test_decoding_metadata_and_download_logs(self):
        from io import BytesIO
        from email.message import Message
        headers = Message()
        headers.add_header('Content-Type','image/jpeg')
        class Reply(BytesIO):
            def geturl(self): return 'https://cdn.plnspttrs.net/image.jpg'
            def getcode(self): return 200
            @property
            def headers(self): return headers
        with patch('aeroscope.data.urllib.request.urlopen', return_value=Reply(b'\xff\xd8\xffimage')):
            with self.assertLogs('aeroscope.photos', 'INFO') as log:
                payload = download_thumbnail('https://cdn.plnspttrs.net/image.jpg')
        self.assertTrue(payload.startswith(b'\xff\xd8'))
        self.assertIn('HTTP 200', '\n'.join(log.output))

if __name__ == '__main__': unittest.main()
