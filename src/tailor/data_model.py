"""Data model for the tailor app.

Implements a model to contain the data values as a backend for the
table view used in the app. This class provides an API specific to Tailor.
"""

import re

import asteval
import numpy as np
import pandas as pd

# treat Inf and -Inf as missing values (e.g. when calling dropna())
pd.options.mode.use_inf_as_na = True


class DataModel:
    """Data model for the tailor app.

    Implements a model to contain the data values as a backend for the
    table view used in the app. This class provides an API specific to Tailor.
    """

    _new_col_num = 0

    def __init__(self) -> None:
        self._data = pd.DataFrame()
        self._col_names = {}
        self._calculated_column_expression = {}
        self._is_calculated_column_valid = {}

    def num_rows(self):
        """Return the number of rows in the table."""
        return len(self._data)

    def num_columns(self):
        """Return the number of columns in the table."""
        return len(self._data.columns)

    def get_value(self, row: int, column: int):
        """Get value at row, column in table

        Args:
            row (int): row number
            column (int): column number
        """
        return self._data.iat[row, column]

    def set_value(self, row: int, column: int, value: float):
        """Set value at row, column in table.

        Args:
            row (int): row number
            column (int): column number
            value (float): value to insert
        """
        self._data.iat[row, column] = value

    def insert_rows(self, row: int, count: int):
        """Insert rows into the table.

        Insert `count` rows into the table at position `row`.

        Args:
            row: an integer row number to indicate the place of insertion.
            count: number of rows to insert
        """
        new_data = pd.DataFrame.from_dict(
            {col: count * [np.nan] for col in self._data.columns}
        )
        self._data = pd.concat(
            [self._data.iloc[:row], new_data, self._data.iloc[row:]]
        ).reset_index(drop=True)

    def remove_rows(self, row: int, count: int):
        """Remove rows from the table.

        Removes a row at the specified row number.

        Args:
            row (int): the first row to remove.
            count (int): the number of rows to remove.
        """
        self._data = self._data.drop(index=range(row, row + count)).reset_index(
            drop=True
        )

    def insert_columns(self, column: int, count: int):
        """Insert columns into the table.

        Insert columns *before* the specified column number.

        Args:
            column (int): a column number to indicate the place of insertion.
            count (int): the number of columns to insert.

        Returns:
            A list of inserted column labels.
        """
        labels = [self._create_new_column_label() for _ in range(count)]
        for idx, label in zip(range(column, column + count), labels):
            self._data.insert(idx, label, np.nan)
            self._col_names[label] = label
        return labels

    def remove_columns(self, column: int, count: int):
        """Remove columns from the table.

        Removes a column at the specified column number.

        Args:
            column (int): a column number to indicate the place of removal.
            count (int): the number of columns to remove.
        """
        labels = self._data.columns[column : column + count]
        self._data.drop(columns=labels, inplace=True)
        for label in labels:
            try:
                del self._calculated_column_expression[label]
            except KeyError:
                # not a calculated column
                pass
        self.recalculate_all_columns()

    def move_column(self, source: int, dest: int):
        """Move a column in the table.

        Moves a column from the source index to the dest index. Contrary to Qt
        conventions the dest index is the index in the final table, _after_ the
        move operation is completed. So, if you have the initial state:

            col0, col1, col2, col3

        and you want to end up with the final state:

            col1, col2, col0, col3

        you should call `move_column(0, 2)` to move col0 from index 0 to index
        2. By Qt conventions, you should call the Qt function with
        `moveColumn(0, 3)` because you want to place col0 _before_ col3. So pay
        attention to the correct arguments.

        Args:
            source (int): the original index of the column
            dest (int): the final index of the column
        """
        cols = list(self._data.columns)
        cols.insert(dest, cols.pop(source))
        self._data = self._data.reindex(columns=cols)

    def is_empty(self):
        """Check whether all cells are empty."""
        # check for *all* nans in a row or column
        return self._data.dropna(how="all").empty

    def insert_calculated_column(self, column: int):
        """Insert a calculated column.

        Insert a column *before* the specified column number. Returns True if
        the insertion was succesful.

        Args:
            column (int): an integer column number to indicate the place of
                insertion.
        """
        (label,) = self.insert_columns(column, count=1)
        self._calculated_column_expression[label] = None
        self._is_calculated_column_valid[label] = False

    def rename_column(self, label: str, name: str):
        """Rename a column.

        Args:
            label (str): the column label
            name (str): the new name for the column
        """
        old_name = self.get_column_name(label)
        new_name = self.normalize_column_name(name)
        self._col_names[label] = new_name

        # FIXME rename all expressions

        # FIXME self.headerDataChanged.emit(QtCore.Qt.Horizontal, col_idx, col_idx)
        # FIXME self.show_status("Renamed column.")

    def normalize_column_name(self, name):
        """Normalize column name.

        Change whitespace to underscores and add an underscore if the name
        starts with a number.

        Args:
            name (str): the name to normalize.

        Returns:
            str: the normalized name.
        """
        return re.sub(r"\W|^(?=\d)", "_", name)

    def update_column_expression(self, col_idx, expression):
        """Update a calculated column with a new expression.

        Args:
            col_idx: an integer column number.
            expression: a string with a mathematical expression used to
                calculate the column values.
        """
        col_name = self.get_column_name(col_idx)
        if self.is_calculated_column(col_idx):
            self._calculated_column_expression[col_name] = expression
            if self.recalculate_column(col_name, expression):
                # calculation was successful
                self.show_status("Updated column values.")

    def recalculate_column(self, col_name, expression=None):
        """Recalculate column values.

        Calculate column values based on its expression. Each column can use
        values from columns to the left of itself. Those values can be accessed
        by using the column name as a variable in the expression.

        Args:
            col_name: a string containing the column name.
            expression: an optional string that contains the mathematical
                expression. If None (the default) the expression is taken from the
                column information.

        Returns:
            True if the calculation was successful, False otherwise.
        """
        # UI must be updated to reflect changes in column values
        # FIXME how to handle this in UI layer
        # self.emit_column_changed(col_name)

        if expression is None:
            # expression must be retrieved from column information
            expression = self._calculated_column_expression[col_name]

        # set up interpreter
        objects = self._get_accessible_columns(col_name)
        aeval = asteval.Interpreter(usersyms=objects)
        try:
            # try to evaluate expression and cast output to a float (series)
            output = aeval(expression, show_errors=False, raise_errors=True)
            if isinstance(output, pd.Series) or isinstance(output, np.ndarray):
                output = output.astype("float64")
            else:
                output = float(output)
        except Exception as exc:
            # error in evaluation or output cannot be cast to a float (series)
            self._is_calculated_column_valid[col_name] = False
            # FIXME self.show_status(f"Error evaluating expression: {exc}")
            return False
        else:
            # evaluation was successful
            self._data[col_name] = output
            self._is_calculated_column_valid[col_name] = True
            # FIXME self.show_status(f"Recalculated column values.")
            return True

    def _get_accessible_columns(self, col_name):
        """Get accessible column data for use in expressions.

        When calculating column values each column can access the values of the
        columns to its left by using the column name as a variable. This method
        returns the column data for the accessible columns.

        Args:
            col_name (str): the name of the column that wants to access data.

        Returns:
            dict: a dictionary of column_name, data pairs.
        """
        # accessible columns to the left of current column
        idx = self._data.columns.get_loc(col_name)
        accessible_columns = self._data.columns[:idx]
        data = {
            k: self._data[k]
            for k in accessible_columns
            if self.is_column_valid(col_name=k)
        }
        return data

    def recalculate_all_columns(self):
        """Recalculate all columns.

        If data is entered or changed, the calculated column values must be
        updated. This method will manually recalculate all column values, from left to right.
        """
        # FIXME
        return
        column_names = self.get_column_names()
        for col_idx in range(self.num_columns()):
            if self.is_calculated_column(col_idx):
                self.recalculate_column(column_names[col_idx])

    def get_column_label(self, column: int):
        """Get column label.

        Get column label at the given index.

        Args:
            column: an integer column number.

        Returns:
            The column label as a string.
        """
        return self._data.columns[column]

    def get_column_name(self, label: str):
        """Get column name.

        Get column name at the given index.

        Args:
            label (str): the column label.

        Returns:
            The column name as a string.
        """
        return self._col_names[label]

    # FIXME
    # def get_column_names(self):
    #     """Get list of all column names."""
    #     return list(self._data.columns)

    def get_column_expression(self, label: str):
        """Get column expression.

        Get the mathematical expression used to calculate values in the
        calculated column.

        Args:
            label (str): the column label.

        Returns:
            A string containing the mathematical expression or None.
        """
        return self._calculated_column_expression.get(label, None)

    def get_column(self, label: str):
        """Return column values.

        Args:
            label (str): the column label.

        Returns:
            An np.ndarray containing the column values.
        """
        return self._data[label].to_numpy()

    def is_calculated_column(self, label: str):
        """Check if column is calculated.

        Checks whether a column is calculated from a mathematical expression.

        Args:
            label (str): the column label.

        Returns:
            True if the column is calculated, False otherwise.
        """
        return label in self._calculated_column_expression

    def is_column_valid(self, label: str):
        """Check if a column has valid values.

        Checks whether the column contains the results of a valid calculation if
        it is a calculated column. When a calculation fails due to an invalid
        expression the values are invalid. If it is a regular data column, the
        values are always valid.

        Args:
            label (str): the column label.

        Returns:
            True if the column values are valid, False otherwise.
        """
        if not self.is_calculated_column(label):
            # values are not calculated, so are always valid
            return True
        else:
            return self._is_calculated_column_valid[label]

    def _create_new_column_label(self):
        """Create a label for a new column.

        Creates column labels like col1, col2, etc.

        Returns:
            A string containing the new label.
        """
        self._new_col_num += 1
        return f"col{self._new_col_num}"

    def save_state_to_obj(self, save_obj):
        """Save all data and state to save object.

        Args:
            save_obj: a dictionary to store the data and state.
        """
        save_obj.update(
            {
                "data": self._data.to_dict("list"),
                "calculated_columns": self._calculated_column_expression,
                "new_col_num": self._new_col_num,
            }
        )

    def load_state_from_obj(self, save_obj):
        """Load all data and state from save object.

        Args:
            save_obj: a dictionary that contains the saved data and state.
        """
        self.beginResetModel()
        self._data = pd.DataFrame.from_dict(save_obj["data"])
        self._calculated_column_expression = save_obj["calculated_columns"]
        self._new_col_num = save_obj["new_col_num"]
        self.endResetModel()
        self.recalculate_all_columns()

    def write_csv(self, filename):
        """Write all data to CSV file.

        Args:
            filename: a string containing the full filename.
        """
        self._data.to_csv(filename, index=False)

    def read_csv(
        self,
        filename,
        delimiter=None,
        decimal=".",
        thousands=",",
        header=None,
        skiprows=0,
    ):
        """Read data from CSV file.

        Overwrites all existing data by importing a CSV file.

        Args:
            filename: a string containing the path to the CSV file
            delimiter: a string containing the column delimiter
            decimal: a string containing the decimal separator
            thousands: a string containing the thousands separator
            header: an integer with the row number containing the column names,
                or None.
            skiprows: an integer with the number of rows to skip at start of file
        """
        self.beginResetModel()

        self._data = self._read_csv_into_dataframe(
            filename, delimiter, decimal, thousands, header, skiprows
        )
        self._calculated_column_expression = {}
        self.endResetModel()

    def read_and_concat_csv(
        self,
        filename,
        delimiter=None,
        decimal=".",
        thousands=",",
        header=None,
        skiprows=0,
    ):
        """Read data from CSV file and concatenate with current data.

        Overwrites all existing columns by importing a CSV file, but keeps other
        columns.

        Args:
            filename: a string containing the path to the CSV file
            delimiter: a string containing the column delimiter
            decimal: a string containing the decimal separator
            thousands: a string containing the thousands separator
            header: an integer with the row number containing the column names,
                or None.
            skiprows: an integer with the number of rows to skip at start of file
        """
        self.beginResetModel()

        import_data = self._read_csv_into_dataframe(
            filename, delimiter, decimal, thousands, header, skiprows
        )
        # drop imported columns from existing data, ignore missing columns
        old_data = self._data.drop(import_data.columns, axis="columns", errors="ignore")
        # concatenate imported and old data
        new_data = pd.concat([import_data, old_data], axis="columns")
        # drop excess rows, if imported data is shorter than old data
        final_data = new_data.iloc[: len(import_data)]

        # save final data and recalculate values in calculated columns
        self._data = final_data
        self.endResetModel()
        self.recalculate_all_columns()

    def _read_csv_into_dataframe(
        self, filename, delimiter, decimal, thousands, header, skiprows
    ):
        """Read CSV data into pandas DataFrame and normalize columns."""
        df = pd.read_csv(
            filename,
            delimiter=delimiter,
            decimal=decimal,
            thousands=thousands,
            header=header,
            skiprows=skiprows,
        )
        # make sure column names are strings, even for numbered columns
        df.columns = df.columns.astype(str)
        # normalize column names to valid python variable names
        df.columns = df.columns.map(self.normalize_column_name)
        return df
