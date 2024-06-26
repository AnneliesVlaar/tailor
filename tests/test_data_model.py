import pathlib
from unittest.mock import call, sentinel

import numpy as np
import pandas as pd
import pytest
from pytest_mock import MockerFixture

from tailor.csv_format_dialog import FormatParameters
from tailor.data_model import DataModel


@pytest.fixture()
def model() -> DataModel:
    return DataModel()


@pytest.fixture()
def bare_bones_data(model: DataModel) -> DataModel:
    """Create a bare bones data model.

    This is an instance of QDataModel with a very basic data structure (five
    rows, two data columns, one calculated column) and an updated column number
    variable, but nothing else. You can use this to test basic data manipulation
    required by Qt for subclasses of QAbstractDataModel.

    This fixture depends on certain implementation details.
    """
    model._data = pd.DataFrame.from_dict(
        {
            "col1": [1.0, 2.0, 3.0, 4.0, 5.0],
            "col2": [6.0, 7.0, 8.0, 9.0, 10.0],
            "col3": [11.0, 12.0, 13.0, 14.0, 15.0],
        }
    )
    # there is no guaranteed order in _col_names
    model._col_names = {"col2": "y", "col3": "z", "col1": "x"}
    model._calculated_column_expression["col3"] = "col2 + 5"
    model._is_calculated_column_valid["col3"] = True
    model._new_col_num += 3
    return model


@pytest.fixture()
def calc_model(model: DataModel) -> DataModel:
    """Create a data model with multiple calculated columns.

    Note: the inital data values do not correspond with the column expressions.
    If you need the correct values, recalculate the column(s) first.

    This fixture depends on certain implementation details.
    """
    model._data = pd.DataFrame.from_dict(
        {k: [1.0, 2.0, 3.0] for k in ["col1", "col2", "col3", "col4", "col5"]}
    )
    model._col_names = {"col1": "x", "col2": "y", "col3": "z", "col4": "t", "col5": "u"}
    model._calculated_column_expression = {
        "col1": "3.14",
        "col2": "col1 ** 2",
        "col4": "sqrt(col2)",
        "col5": "",
    }
    model._is_calculated_column_valid = {k: True for k in ["col1", "col2", "col4"]}
    model._is_calculated_column_valid["col5"] = False
    return model


@pytest.fixture()
def simple_test_data(model: DataModel) -> DataModel:
    """Create simple test data.

    This fixture does not depend on implementation details, but does make use of
    the DataModel machinery.
    """
    (col1,) = model.insert_columns(0, 1)
    col2 = model.insert_calculated_column(1)
    col3 = model.insert_calculated_column(2)
    model.rename_column(col1, "x")
    model.rename_column(col2, "y")
    model.rename_column(col3, "z")
    model.insert_rows(0, 5)

    model.set_values_from_array(0, 0, np.array([[0.0, 1.0, 2.0, 3.0, 4.0]]).T)
    model.update_column_expression(col2, "x ** 2")
    model.update_column_expression(col3, "x + 1")
    return model


class TestImplementationDetails:
    def test_model_attributes(self, model: DataModel):
        assert type(model._data) == pd.DataFrame
        assert model._new_col_num == 0

    def test_new_column_label(self, model: DataModel):
        labels = [model._create_new_column_label() for _ in range(3)]
        assert labels == ["col1", "col2", "col3"]
        assert model._new_col_num == 3


class TestDataModel:
    def test_num_rows_row_count(self, bare_bones_data: DataModel):
        assert bare_bones_data.num_rows() == 5

    def test_num_columns(self, bare_bones_data: DataModel):
        assert bare_bones_data.num_columns() == 3

    def test_get_value_returns_data(self, bare_bones_data: DataModel):
        assert bare_bones_data.get_value(2, 1) == 8.0
        assert bare_bones_data.get_value(3, 0) == 4.0

    def test_get_values_returns_data(self, bare_bones_data: DataModel):
        values = bare_bones_data.get_values(1, 1, 4, 2)

        assert values.shape == (4, 2)
        assert values.flatten().tolist() == pytest.approx(
            [7.0, 12.0, 8.0, 13.0, 9.0, 14.0, 10.0, 15.0]
        )

    @pytest.mark.parametrize("value", [4.7, np.nan])
    def test_set_value(self, bare_bones_data: DataModel, value):
        bare_bones_data.set_value(2, 1, value)
        assert bare_bones_data.get_value(2, 1) == pytest.approx(value, nan_ok=True)

    def test_set_value_triggers_recalculation(
        self, bare_bones_data: DataModel, mocker: MockerFixture
    ):
        mocker.patch.object(bare_bones_data, "recalculate_columns_from")
        mocker.patch.object(bare_bones_data, "get_column_label")
        bare_bones_data.get_column_label.return_value = sentinel.label

        bare_bones_data.set_value(row=1, column=2, value=3.0)

        # recalculate all columns starting from start_column
        bare_bones_data.get_column_label.assert_called_with(2)
        bare_bones_data.recalculate_columns_from.assert_called_with(sentinel.label)

    def test_set_values(self, bare_bones_data: DataModel):
        # no calculated columns, only data
        bare_bones_data._calculated_column_expression = {}

        bare_bones_data.set_values(
            start_row=1, start_column=1, end_row=3, end_column=2, value=0.0
        )

        data = bare_bones_data._data.to_dict("list")
        assert data["col1"] == pytest.approx([1.0, 2.0, 3.0, 4.0, 5.0])
        assert data["col2"] == pytest.approx([6.0, 0.0, 0.0, 0.0, 10.0])
        assert data["col3"] == pytest.approx([11.0, 0.0, 0.0, 0.0, 15.0])

    def test_set_values_triggers_recalculation(
        self, bare_bones_data: DataModel, mocker: MockerFixture
    ):
        mocker.patch.object(bare_bones_data, "recalculate_columns_from")
        mocker.patch.object(bare_bones_data, "get_column_label")
        bare_bones_data.get_column_label.return_value = sentinel.label

        bare_bones_data.set_values(
            start_row=1, start_column=2, end_row=3, end_column=4, value=0.0
        )

        # recalculate all columns starting from start_column
        bare_bones_data.get_column_label.assert_called_with(2)
        bare_bones_data.recalculate_columns_from.assert_called_with(sentinel.label)

    def test_set_values_from_array(self, bare_bones_data: DataModel):
        # no calculated columns, only data
        bare_bones_data._calculated_column_expression = {}

        bare_bones_data.set_values_from_array(
            start_row=1,
            start_column=1,
            values=np.array([[-1.0, -2.0, -3.0], [-4.0, -5.0, -6.0]]).T,
        )

        data = bare_bones_data._data.to_dict("list")
        assert data["col1"] == pytest.approx([1.0, 2.0, 3.0, 4.0, 5.0])
        assert data["col2"] == pytest.approx([6.0, -1.0, -2.0, -3.0, 10.0])
        assert data["col3"] == pytest.approx([11.0, -4.0, -5.0, -6.0, 15.0])

    def test_set_values_from_array_triggers_recalculation(
        self, bare_bones_data: DataModel, mocker: MockerFixture
    ):
        mocker.patch.object(bare_bones_data, "recalculate_columns_from")
        mocker.patch.object(bare_bones_data, "get_column_label")
        bare_bones_data.get_column_label.return_value = sentinel.label

        bare_bones_data.set_values_from_array(
            start_row=1, start_column=2, values=np.array([[1.0]])
        )

        # recalculate all columns starting from start_column
        bare_bones_data.get_column_label.assert_called_with(2)
        bare_bones_data.recalculate_columns_from.assert_called_with(sentinel.label)

    def test_insert_rows(self, bare_bones_data: DataModel):
        bare_bones_data.insert_rows(3, 4)
        # check that all values in inserted rows are NaN
        # use loc to check that the row labels are reindexed
        assert bool(bare_bones_data._data.loc[3:6].isna().all(axis=None)) is True
        # check insertion using values from col1
        assert list(bare_bones_data._data["col1"]) == pytest.approx(
            [
                1.0,
                2.0,
                3.0,
                np.nan,
                np.nan,
                np.nan,
                np.nan,
                4.0,
                5.0,
            ],
            nan_ok=True,
        )

    def test_insert_rows_triggers_recalculation(
        self, bare_bones_data: DataModel, mocker: MockerFixture
    ):
        mocker.patch.object(bare_bones_data, "recalculate_all_columns")
        bare_bones_data.insert_rows(3, 4)
        bare_bones_data.recalculate_all_columns.assert_called()

    def test_remove_rows(self, bare_bones_data: DataModel):
        bare_bones_data.remove_rows(1, 2)
        assert list(bare_bones_data._data["col1"]) == pytest.approx([1.0, 4.0, 5.0])
        assert list(bare_bones_data._data["col2"]) == pytest.approx([6.0, 9.0, 10.0])
        assert list(bare_bones_data._data.index) == list(range(3))

    def test_insert_columns(self, bare_bones_data: DataModel):
        bare_bones_data.insert_columns(1, 2)
        assert bare_bones_data._data.shape == (5, 5)
        assert list(bare_bones_data._data.iloc[0]) == pytest.approx(
            [1.0, np.nan, np.nan, 6.0, 11.0], nan_ok=True
        )

    def test_insert_columns_labels(self, bare_bones_data: DataModel):
        bare_bones_data.insert_columns(3, 2)
        assert list(bare_bones_data._data.columns) == [
            "col1",
            "col2",
            "col3",
            "col4",
            "col5",
        ]

    def test_insert_columns_names(self, bare_bones_data: DataModel):
        assert "col4" not in bare_bones_data._col_names
        bare_bones_data.insert_columns(0, 1)
        assert bare_bones_data._col_names["col4"] == "col4"

    def test_remove_columns(self, bare_bones_data: DataModel):
        bare_bones_data.remove_columns(1, 2)
        assert bare_bones_data._data.shape == (5, 1)
        assert bare_bones_data._data.columns == ["col1"]

    def test_remove_last_column(self, bare_bones_data: DataModel):
        # this should not crash
        bare_bones_data.remove_columns(2, 1)

    def test_remove_columns_removes_calculated_column(
        self, bare_bones_data: DataModel, mocker: MockerFixture
    ):
        mocker.patch.object(bare_bones_data, "recalculate_columns_from")

        bare_bones_data.remove_columns(column=0, count=1)
        assert len(bare_bones_data._calculated_column_expression) == 1

        bare_bones_data.remove_columns(column=1, count=1)
        assert len(bare_bones_data._calculated_column_expression) == 0

    def test_remove_columns_removes_column_labels(
        self, bare_bones_data: DataModel, mocker: MockerFixture
    ):
        assert "col1" in bare_bones_data._col_names
        bare_bones_data.remove_columns(column=0, count=1)
        assert "col1" not in bare_bones_data._col_names

    def test_remove_columns_calls_recalculate(
        self, bare_bones_data: DataModel, mocker: MockerFixture
    ):
        mocker.patch.object(bare_bones_data, "get_column_label")
        bare_bones_data.get_column_label.return_value = sentinel.label
        mocker.patch.object(bare_bones_data, "recalculate_columns_from")
        bare_bones_data.remove_columns(1, 1)
        bare_bones_data.get_column_label.assert_called_with(1)
        bare_bones_data.recalculate_columns_from.assert_called_with(sentinel.label)

    @pytest.mark.parametrize(
        "source, dest, order",
        [
            (1, 1, ["col1", "col2", "col3"]),
            (0, 1, ["col2", "col1", "col3"]),
            (0, 2, ["col2", "col3", "col1"]),
            (2, 1, ["col1", "col3", "col2"]),
        ],
    )
    def test_move_column(
        self, bare_bones_data: DataModel, mocker: MockerFixture, source, dest, order
    ):
        mocker.patch.object(bare_bones_data, "get_column_label")
        mocker.patch.object(bare_bones_data, "recalculate_columns_from")
        bare_bones_data.get_column_label.return_value = sentinel.label

        bare_bones_data.move_column(source, dest)

        assert list(bare_bones_data._data.columns) == order
        bare_bones_data.get_column_label.assert_called_with(min(source, dest))
        bare_bones_data.recalculate_columns_from.assert_called_with(sentinel.label)

    def test_insert_calculated_column(self, bare_bones_data: DataModel):
        assert len(bare_bones_data._calculated_column_expression) == 1
        assert bare_bones_data._data.shape == (5, 3)

        bare_bones_data.insert_calculated_column(column=1)

        assert len(bare_bones_data._calculated_column_expression) == 2
        assert bare_bones_data._data.shape == (5, 4)
        assert list(bare_bones_data._data.iloc[0]) == pytest.approx(
            [1.0, np.nan, 6.0, 11.0], nan_ok=True
        )

    def test_insert_calculated_column_sets_attributes(
        self, bare_bones_data: DataModel, mocker: MockerFixture
    ):
        mocker.patch.object(bare_bones_data, "insert_columns")
        bare_bones_data.insert_columns.return_value = [sentinel.label]

        bare_bones_data.insert_calculated_column(column=1)

        assert bare_bones_data._calculated_column_expression[sentinel.label] == ""
        assert bare_bones_data._is_calculated_column_valid[sentinel.label] is False

    def test_insert_calculated_column_returns_label(self, bare_bones_data: DataModel):
        label = bare_bones_data.insert_calculated_column(column=0)
        assert label.startswith("col")

    def test_get_column_label(self, bare_bones_data: DataModel):
        expected = ["col1", "col2", "col3"]
        actual = [bare_bones_data.get_column_label(idx) for idx in range(3)]
        assert actual == expected

    def test_get_column_label_by_name(self, bare_bones_data: DataModel) -> None:
        names = ["x", "y", "z"]
        expected = ["col1", "col2", "col3"]
        actual = [bare_bones_data.get_column_label_by_name(name) for name in names]
        assert actual == expected

    def test_get_column_labels(self, bare_bones_data: DataModel):
        # column labels must be in the order they appear in the data
        expected = ["col1", "col2", "col3"]
        actual = bare_bones_data.get_column_labels()
        assert actual == expected

    def test_get_column_name(self, bare_bones_data: DataModel):
        labels = ["col1", "col2", "col3"]
        expected = ["x", "y", "z"]
        actual = [bare_bones_data.get_column_name(label) for label in labels]
        assert actual == expected

    def test_get_column_names(self, bare_bones_data: DataModel):
        # column names must be in the order they appear in the data
        expected = ["x", "y", "z"]
        assert bare_bones_data.get_column_names() == expected

    def test_get_column(self, bare_bones_data: DataModel):
        expected = [6.0, 7.0, 8.0, 9.0, 10.0]
        actual = bare_bones_data.get_column("col2")
        assert isinstance(actual, np.ndarray)
        assert list(actual) == pytest.approx(expected)

    def test_rename_column(self, bare_bones_data: DataModel):
        name = "t null"
        expected = "t_null"

        # rewrites spaces to underscores
        new_name = bare_bones_data.rename_column("col1", name)

        assert new_name == expected
        assert bare_bones_data.get_column_name("col1") == expected

    def test_normalize_column_name(self, model: DataModel):
        assert model.normalize_column_name("t x y") == "t_x_y"
        assert model.normalize_column_name("  x") == "__x"
        assert model.normalize_column_name("x  ") == "x__"
        assert model.normalize_column_name("1x") == "_1x"

    def test_is_calculated_column(self, bare_bones_data: DataModel):
        assert bare_bones_data.is_calculated_column("col1") is False
        assert bare_bones_data.is_calculated_column("col3") is True

    def test_is_column_valid(self, bare_bones_data: DataModel):
        # not calculated
        assert bare_bones_data.is_column_valid("col1") is True
        # calculated, valid
        assert bare_bones_data.is_calculated_column("col3") is True
        assert bare_bones_data.is_column_valid("col3") is True
        # just added, not yet a valid expression
        bare_bones_data.insert_calculated_column(0)
        assert bare_bones_data.is_calculated_column("col4") is True
        assert bare_bones_data.is_column_valid("col4") is False

    def test_get_column_expression(self, bare_bones_data: DataModel):
        # variables are renamed from column labels -> names
        assert bare_bones_data.get_column_expression("col3") == "y + 5"

    def test_get_column_expression_returns_None_for_data_column(
        self, bare_bones_data: DataModel
    ):
        assert bare_bones_data.get_column_expression("col1") is None
        assert bare_bones_data.get_column_expression("doesnotexist") is None

    def test_get_column_expression_returns_None_for_empty_expression(
        self, calc_model: DataModel
    ):
        assert calc_model.get_column_expression("col5") is None
        assert calc_model.get_column_expression("doesnotexist") is None

    def test_get_column_expression_with_syntax_error(self, bare_bones_data: DataModel):
        bare_bones_data._calculated_column_expression["col3"] = "y *"
        # should not raise a syntax error but return expression as is
        assert bare_bones_data.get_column_expression("col3") == "y *"

    def test_get_column_expression_locks_in_variable(
        self, bare_bones_data: DataModel, mocker: MockerFixture
    ):
        mocker.patch.object(bare_bones_data, "update_column_expression")
        # stored expression should not contain variable names but labels
        bare_bones_data._calculated_column_expression["col3"] = "y + 5"

        bare_bones_data.get_column_expression("col3")

        # update_column_expression will try renaming variable to label
        bare_bones_data.update_column_expression.assert_called_with("col3", "y + 5")

    def test_get_column_expression_prevents_infinite_locking_loop(
        self, bare_bones_data: DataModel, mocker: MockerFixture
    ):
        mocker.patch.object(bare_bones_data, "update_column_expression")
        # stored expression should not contain variable names but labels
        # but if columns are still named col1, col2, etc. false positives may
        # occur resulting in a infinite rename loop.
        bare_bones_data._col_names = {"col1": "col1", "col2": "col2", "col3": "col3"}
        bare_bones_data._calculated_column_expression["col3"] = "col1 + 5"

        bare_bones_data.get_column_expression("col3")

        # update_column_expression will try renaming variable to label
        bare_bones_data.update_column_expression.assert_not_called()

    def test_update_column_expression(
        self, bare_bones_data: DataModel, mocker: MockerFixture
    ):
        mocker.patch.object(bare_bones_data, "recalculate_columns_from")

        bare_bones_data.update_column_expression("col3", "y + 5")

        # expression variables are stored using column labels, not names
        assert bare_bones_data._calculated_column_expression["col3"] == "col2 + 5"
        bare_bones_data.recalculate_columns_from.assert_called_with("col3")

    def test_update_column_expression_nop(self, bare_bones_data: DataModel):
        # col1 is not a calculated column
        bare_bones_data.update_column_expression("col1", "x ** 2")
        assert "col1" not in bare_bones_data._calculated_column_expression

    def test_update_column_expression_with_syntax_error(
        self, bare_bones_data: DataModel, mocker: MockerFixture
    ) -> None:
        mocker.patch.object(bare_bones_data, "recalculate_columns_from")
        bare_bones_data.update_column_expression("col3", "y*")
        assert bare_bones_data._calculated_column_expression["col3"] == "y*"

    def test_recalculate_columns_from(
        self, calc_model: DataModel, mocker: MockerFixture
    ):
        mocker.patch.object(calc_model, "recalculate_column")

        calc_model.recalculate_columns_from("col2")

        expected = [call("col2"), call("col4"), call("col5")]
        assert calc_model.recalculate_column.call_args_list == expected

    def test_recalculate_all_columns(
        self, calc_model: DataModel, mocker: MockerFixture
    ):
        mocker.patch.object(calc_model, "recalculate_column")

        calc_model.recalculate_all_columns()

        expected = [call("col1"), call("col2"), call("col4"), call("col5")]
        assert calc_model.recalculate_column.call_args_list == expected

    def test_accessible_columns_are_present(self, calc_model: DataModel):
        # accessible objects are returned by their names
        objects = calc_model._get_accessible_columns("col3")
        assert "x" in objects
        assert "y" in objects
        assert "t" not in objects

    def test_invalid_columns_are_not_accessible(self, calc_model: DataModel):
        calc_model._is_calculated_column_valid["col1"] = False
        objects = calc_model._get_accessible_columns("col2")
        assert "x" not in objects

    def test_accessible_column_values(self, calc_model: DataModel):
        objects = calc_model._get_accessible_columns("col2")
        assert objects["x"] is calc_model._data["col1"]

    def test_recalculate_column_as_series(
        self, calc_model: DataModel, mocker: MockerFixture
    ):
        mocker.patch.object(calc_model, "get_column_expression")
        calc_model.get_column_expression.return_value = "x ** 2"

        is_valid = calc_model.recalculate_column("col2")

        assert is_valid is True
        assert calc_model.is_column_valid("col2") is True
        assert list(calc_model._data["col2"]) == pytest.approx([1.0, 4.0, 9.0])

    def test_recalculate_column_as_array(
        self, calc_model: DataModel, mocker: MockerFixture
    ):
        mocker.patch.object(calc_model, "get_column_expression")
        calc_model.get_column_expression.return_value = "gradient(x)"

        is_valid = calc_model.recalculate_column("col2")

        assert is_valid is True
        assert calc_model.is_column_valid("col2") is True

    def test_recalculate_column_as_integer(
        self, calc_model: DataModel, mocker: MockerFixture
    ):
        mocker.patch.object(calc_model, "get_column_expression")
        calc_model.get_column_expression.return_value = "4"

        is_valid = calc_model.recalculate_column("col2")

        assert is_valid is True
        assert calc_model.is_column_valid("col2") is True
        assert calc_model._data["col2"].dtype == np.float64

    def test_recalculate_column_using_invalid_data(
        self, calc_model: DataModel, mocker: MockerFixture
    ):
        mocker.patch.object(calc_model, "get_column_expression")
        calc_model.get_column_expression.return_value = "col3 ** 2"

        is_valid = calc_model.recalculate_column("col2")

        assert is_valid is False
        assert calc_model.is_column_valid("col2") is False

    def test_export_csv(
        self, simple_test_data: DataModel, tmp_path: pathlib.Path
    ) -> None:
        data_path = tmp_path / "testdata.csv"
        simple_test_data.export_csv(data_path)

        contents = data_path.read_text()

        assert (
            contents
            == """\
x,y,z
0.0,0.0,1.0
1.0,1.0,2.0
2.0,4.0,3.0
3.0,9.0,4.0
4.0,16.0,5.0
"""
        )

    def test_create_df_from_csv(self, model: DataModel, tmp_path: pathlib.Path) -> None:
        data_path = tmp_path / "testdata.csv"
        data_path.write_text(
            """\
1,2
0.0,0.0
1.0,2.0
3.0,4.0                                                     
"""
        )

        df = model.create_df_from_csv(data_path, FormatParameters())

        assert list(df.columns) == ["_1", "_2"]
        data = df.to_dict("list")
        assert data["_1"] == pytest.approx([0.0, 1.0, 3.0])
        assert data["_2"] == pytest.approx([0.0, 2.0, 4.0])

    def test_import_csv(self, model: DataModel, tmp_path: pathlib.Path) -> None:
        # data can be imported into sheet with some empty columns
        model.insert_columns(0, 2)
        data_path = tmp_path / "testdata.csv"
        data_path.write_text(
            """\
x,y
0.0,0.0
1.0,2.0
3.0,4.0
"""
        )

        model.import_csv(data_path, FormatParameters())

        assert model.get_column_labels() == ["col1", "col2"]
        assert model.get_column_names() == ["x", "y"]
        assert list(model.get_values(0, 1, 2, 1)) == pytest.approx([0.0, 2.0, 4.0])

    def test_merge_csv(self, simple_test_data: DataModel, tmp_path) -> None:
        data_path = tmp_path / "testdata.csv"
        data_path.write_text(
            """\
x,t,z
1.0,1.0,0.0
3.0,2.0,1.0
5.0,3.0,2.0
7.0,4.0,3.0
"""
        )
        assert simple_test_data.is_calculated_column("col3") is True

        simple_test_data.merge_csv(data_path, FormatParameters())

        assert simple_test_data.num_columns() == 4
        # columns from csv file are placed at beginning of the sheet
        assert simple_test_data.get_column_names() == ["x", "t", "z", "y"]
        assert simple_test_data.get_column_labels() == ["col1", "col4", "col3", "col2"]
        assert simple_test_data.get_column("col2") == pytest.approx(
            [1.0, 9.0, 25.0, 49.0]
        )
        # col3 (z) is no longer calculated, but data from imported CSV
        assert simple_test_data.is_calculated_column("col3") is False
