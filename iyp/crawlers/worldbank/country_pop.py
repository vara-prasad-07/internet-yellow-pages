import argparse
import json
import logging
import sys
from datetime import datetime, timezone

import requests

from iyp import BaseCrawler

URL = 'https://api.worldbank.org/v2/country/all/indicator/SP.POP.TOTL?per_page=400&mrv=1&format=json'
ORG = 'WorldBank'
NAME = 'worldbank.country_pop'


class Crawler(BaseCrawler):
    def __init__(self, organization, url, name):
        super().__init__(organization, url, name)
        self.reference['reference_url_info'] = (
            'https://datahelpdesk.worldbank.org/knowledgebase/articles/'
            '889392-about-the-indicators-api-documentation'
        )

    def run(self):
        """Get country population from Worldbank API and push it to IYP."""

        # Get content
        req = requests.get(URL)
        req.raise_for_status()
        content = json.loads(req.content)

        # Set last time of modification
        self.reference['reference_time_modification'] = datetime.strptime(content[0]['lastupdated'],
                                                                          '%Y-%m-%d').replace(tzinfo=timezone.utc)

        # Get countries present in IYP cc to id mapping
        country_ids = self.iyp.batch_get_nodes_by_single_prop('Country', 'country_code', create=False, all=True)

        # Get countries and population from World Bank
        lines = set()
        for entry in content[1]:

            country = entry['country']['id']
            if country not in country_ids or not entry['value']:
                continue

            population = entry['value']
            lines.add((country, population))

        # Get `Estimate` node ID
        estimate_qid = self.iyp.get_node('Estimate', properties={'name': 'World Bank Population Estimate'})

        # Compute links
        links = []
        for (country, population) in lines:

            country_qid = country_ids[country]

            links.append({'src_id': country_qid, 'dst_id': estimate_qid,
                         'props': [self.reference, {'value': population}]})

        # Push all links to IYP
        self.iyp.batch_add_links('POPULATION', links)

    def unit_test(self):
        return super().unit_test(['POPULATION'])


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--unit-test', action='store_true')
    args = parser.parse_args()

    FORMAT = '%(asctime)s %(levelname)s %(message)s'
    logging.basicConfig(
        format=FORMAT,
        filename='log/' + NAME + '.log',
        level=logging.INFO,
        datefmt='%Y-%m-%d %H:%M:%S'
    )

    logging.info(f'Started: {sys.argv}')

    crawler = Crawler(ORG, URL, NAME)
    if args.unit_test:
        crawler.unit_test()
    else:
        crawler.run()
        crawler.close()
    logging.info(f'Finished: {sys.argv}')


if __name__ == '__main__':
    main()
    sys.exit(0)
