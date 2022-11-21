from datetime import date
import sys
import logging
from collections import defaultdict
from datetime import datetime, timedelta
import requests
from iyp import BaseCrawler

# URL to RIPE repository
URL = 'https://ftp.ripe.net/rpki/'
ORG = 'RIPE NCC'

TALS = ['afrinic.tal', 'apnic.tal', 'arin.tal', 'lacnic.tal', 'ripencc.tal']

class Crawler(BaseCrawler):
    def __init__(self, organization, url):
        """Initialize IYP and statements for pushed data"""

        now = datetime.utcnow()
        self.date_path = f'{now.year}/{now.month:02d}/{now.day:02d}'

        # Check if today's data is available
        self.url = f'{URL}/afrinic.tal/{self.date_path}/roas.csv'
        req = requests.head( self.url )
        if req.status_code != 200:
            now -= timedelta(days=1)
            self.date_path = f'{now.year}/{now.month:02d}/{now.day:02d}'
            logging.warning("Today's data not yet available!")
            logging.warning("Using yesterday's data: "+self.date_path)

        super().__init__(organization, url)

    def run(self):
        """Fetch data from RIPE and push to IYP. """

        for tal in TALS:

            self.url = f'{URL}/{tal}/{self.date_path}/roas.csv'
            logging.info(f'Fetching ROA file: {self.url}')
            req = requests.get( self.url )
            if req.status_code != 200:
                sys.exit('Error while fetching data for '+self.url)
            
            # Aggregate data per prefix
            prefix_info = defaultdict(list)
            for line in req.text.splitlines():
                url, asn, prefix, max_length, start, end = line.split(',')
                
                # Skip header
                if url=='URI':
                    continue

                prefix_info[prefix].append({
                    'url': url, 
                    'asn': asn, 
                    'max_length': max_length, 
                    'start': start, 
                    'end': end})

            for i, (prefix, attributes) in enumerate(prefix_info.items()):
                self.update(prefix, attributes)
                sys.stderr.write(f'\rProcessing {self.url}... {i+1} prefixes ({prefix})     ')

    def update(self, prefix, attributes):
        """Add the prefix to IYP if it's not already there and update its
        properties."""

        statements = []
        for att in attributes:
        
            vrp = {
                    'notBefore': att['start'],
                    'notAfter': att['end'],
                    'uri': att['url'],
                    'maxLength': att['max_length']
                  }

            # Properties
            asn_qid = self.iyp.get_node('AS', {'asn': att['asn'].replace('AS','')}, create=True)
            if asn_qid is None:
                print('Error: ', prefix, attributes)
                return

            statements.append(
                        [ 'ROUTE_ORIGIN_AUTHORIZATION',
                            asn_qid,
                            dict(vrp, **self.reference),
                        ]
                    )

        # Commit to IYP
        # Get the prefix QID (create if prefix is not yet registered) and commit changes
        af = 6
        if '.' in prefix:
            af = 4
        prefix_qid = self.iyp.get_node( 'PREFIX', {'prefix': prefix, 'af': af}, create=True ) 
        self.iyp.add_links( prefix_qid, statements )
        
# Main program
if __name__ == '__main__':

    scriptname = sys.argv[0].replace('/','_')[0:-3]
    FORMAT = '%(asctime)s %(processName)s %(message)s'
    logging.basicConfig(
            format=FORMAT, 
            filename='log/'+scriptname+'.log',
            level=logging.INFO, 
            datefmt='%Y-%m-%d %H:%M:%S'
            )
    logging.info("Started: %s" % sys.argv)

    crawler = Crawler(ORG, URL)
    crawler.run()
    crawler.close()
