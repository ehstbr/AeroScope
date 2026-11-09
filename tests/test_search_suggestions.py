"""Search suggestions are testable without GTK or network access."""
import unittest
from types import SimpleNamespace
from aeroscope.search_suggestions import (
    SearchSuggestion, normalized, relevance, local_suggestions,
    city_suggestions, grouped_suggestions,
)

class SuggestionTests(unittest.TestCase):
    def setUp(self):
        self.aircraft = [
            SimpleNamespace(hex='e48df5', flight='TAM3434', registration='PT-MUJ',
                            model='B772', lat=-20.1, lon=-44.9),
            SimpleNamespace(hex='a0b0c0', flight='AZU4033', registration='PS-AEM',
                            model='E295', lat=-20.2, lon=-44.8),
        ]
        self.airports = {
            'CNF': ('SBCF', 'Belo Horizonte / Confins', -19.6244, -43.9719),
            'DIQ': ('SNDV', 'Divinópolis', -20.1807, -44.8704),
            'GRU': ('SBGR', 'São Paulo / Guarulhos', -23.4356, -46.4731),
        }

    def test_accent_insensitive(self):
        self.assertEqual(normalized('São  Paulo'), 'sao paulo')
        self.assertEqual(relevance('divinopolis', 'Divinópolis'), 0)
        self.assertEqual(relevance('PTMUJ', 'PT-MUJ'), 0)

    def test_aircraft_flight_registration_and_model(self):
        model_name = lambda m: {'B772':'Boeing 777-200', 'E295':'Embraer E195-E2'}[m]
        for query in ('TAM3434','PTMUJ','E48DF5','777'):
            with self.subTest(query=query):
                rows = local_suggestions(query, self.aircraft, self.airports, model_name)
                self.assertEqual(rows[0].kind, 'aircraft')
                self.assertEqual(rows[0].key, 'e48df5')

    def test_airport_codes_or_name(self):
        for query in ('SBCF', 'cnf', 'confins'):
            rows = local_suggestions(query, self.aircraft, self.airports)
            self.assertEqual(rows[0].kind, 'airport')
            self.assertEqual(rows[0].key, 'CNF')
        self.assertEqual(local_suggestions('sao paulo', [], self.airports)[0].key, 'GRU')

    def test_city_from_geocoder_and_grouping(self):
        rows = city_suggestions('sao', [('São Paulo','São Paulo','Brasil',-23.55,-46.63),
                                       ('São Paulo','São Paulo','Brasil',-23.55,-46.63),
                                       ('São Pedro','SP','Brasil',-22.55,-47.91),
                                       ('Manaus','Amazonas','Brasil',-3.1,-60.0)])
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].kind, 'city')
        self.assertEqual(rows[0].title, 'São Paulo')
        grouped = grouped_suggestions([
            SearchSuggestion('city','c','Cidade','estado'),
            SearchSuggestion('airport','a','Aeroporto','iata'),
            SearchSuggestion('aircraft','x','Voo','hex')])
        self.assertEqual([key for key, _ in grouped], ['aircraft','airport','city'])

    def test_no_network_calls_or_fake_city_coordinates(self):
        self.assertEqual(local_suggestions('inexistente', self.aircraft, self.airports), [])
        self.assertEqual(city_suggestions('city',[('City','','',999,0)]),[])

if __name__ == '__main__': unittest.main()
