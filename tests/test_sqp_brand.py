"""The SQP brand, from the metadata row Amazon writes above the header of its CSV and XLSX exports."""
import io

import openpyxl
from streamlit.proto.Common_pb2 import FileURLs
from streamlit.runtime.uploaded_file_manager import UploadedFile, UploadedFileRec

from core.helpers import extract_sqp_brand, read_sqp

AMAZON_CSV = (
    '"Brand=[""Mott & Bow""]","Reporting Range=[""Weekly""]","Select week=[""Week 38 | 2026""]"\n'
    '"Search Query","Search Query Score","Search Query Volume","Impressions: Total Count"\n'
    '"mott and bow t shirts","1","900","9000"\n'
)
HEADER_ONLY_CSV = (
    '"Search Query","Search Query Score","Search Query Volume","Impressions: Total Count"\n'
    '"mott and bow t shirts","1","900","9000"\n'
)
HEADER = ["Search Query", "Search Query Score"]


def _upload(name: str, data: bytes) -> UploadedFile:
    return UploadedFile(UploadedFileRec(file_id=name, name=name, type="", data=data), FileURLs())


def _amazon_xlsx() -> bytes:
    book = openpyxl.Workbook()
    sheet = book.active
    sheet.append(['Brand=["Mott & Bow"]', 'Reporting Range=["Weekly"]', 'Select week=["Week 38 | 2026"]'])
    sheet.append(["Search Query", "Search Query Score", "Search Query Volume", "Impressions: Total Count"])
    sheet.append(["mott and bow t shirts", 1, 900, 9000])
    buffer = io.BytesIO()
    book.save(buffer)
    return buffer.getvalue()


def test_the_brand_of_amazons_csv_comes_from_its_metadata_row_lowercased():
    assert extract_sqp_brand(_upload("sqp.csv", AMAZON_CSV.encode("utf-8"))) == "mott & bow"


def test_a_csv_saved_again_by_excel_with_a_byte_order_mark_keeps_its_brand():
    assert extract_sqp_brand(_upload("sqp.csv", AMAZON_CSV.encode("utf-8-sig"))) == "mott & bow"


def test_after_the_brand_the_csv_is_read_from_its_header_row():
    upload = _upload("sqp.csv", AMAZON_CSV.encode("utf-8"))

    extract_sqp_brand(upload)

    assert upload.tell() == 0
    assert list(read_sqp.__wrapped__(upload).columns[:2]) == HEADER


def test_the_brand_of_amazons_xlsx_comes_from_its_metadata_row_and_the_file_is_read_from_its_header_row():
    upload = _upload("sqp.xlsx", _amazon_xlsx())

    assert extract_sqp_brand(upload) == "mott & bow"
    assert upload.tell() == 0
    assert list(read_sqp.__wrapped__(upload).columns[:2]) == HEADER


def test_a_csv_without_the_metadata_row_has_no_brand_and_is_left_at_its_start():
    upload = _upload("sqp.csv", HEADER_ONLY_CSV.encode("utf-8"))

    assert extract_sqp_brand(upload) is None
    assert upload.tell() == 0


def test_an_unreadable_file_has_no_brand_and_the_log_says_why(caplog):
    upload = _upload("sqp.csv", b"")

    assert extract_sqp_brand(upload) is None
    assert upload.tell() == 0
    assert "SQP brand unreadable from sqp.csv" in caplog.text
