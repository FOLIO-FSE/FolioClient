import pycounter.sushi
import datetime

report = pycounter.sushi.get_report(
    wsdl_url="https://jusp.jisc.ac.uk/sushiservice/r4/",
    start_date=datetime.date(2015, 1, 1),
    end_date=datetime.date(2020, 1, 31),
    requestor_id="dum",
    customer_reference="30",
    report="JR1",
)
for journal in report:
    print(journal.title)
