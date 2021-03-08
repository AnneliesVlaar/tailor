"""Tab widget containing plot with associated user interface.

A widget containing a scatter plot of some data columns with user interface
elements to specify a mathematical model to fit to the model.
"""

from PyQt5 import uic, QtWidgets
import pyqtgraph as pg
import pkg_resources
import numpy as np
import matplotlib.pyplot as plt
from lmfit import models
import asteval


NUM_POINTS = 1000
MSG_TIMEOUT = 5000


class VariableError(RuntimeError):
    pass


class PlotTab(QtWidgets.QWidget):
    """Tab widget containing plot with associated user interface.

    A widget containing a scatter plot of some data columns with user interface
    elements to specify a mathematical model to fit to the model.
    """

    x = None
    y = None
    x_err = None
    y_err = None
    err_width = None
    err_height = None

    def __init__(self, data_model, main_window):
        """Initialize the widget.

        Args:
            data_model: the data model holding the data.
        """
        super().__init__()

        self.data_model = data_model
        uic.loadUi(
            pkg_resources.resource_stream("tailor.resources", "plot_tab.ui"), self
        )

        self.main_window = main_window

        self.param_layout = QtWidgets.QVBoxLayout()
        self.param_layout.setContentsMargins(4, 0, 0, 0)
        self.parameter_box.setLayout(self.param_layout)
        self._params = {}
        self._symbols = set(asteval.Interpreter().symtable.keys())

        # FIXME move this to create_plot, or vice versa?
        self._initial_param_plot = self.plot_widget.plot(
            symbol=None, pen=pg.mkPen(color="b", width=2)
        )
        self._fit_plot = self.plot_widget.plot(
            symbol=None, pen=pg.mkPen(color="r", width=2)
        )

        self.model_func.textEdited.connect(self.update_fit_params)
        self.fit_button.clicked.connect(self.perform_fit)
        self.xlabel.textChanged.connect(self.update_xlabel)
        self.ylabel.textChanged.connect(self.update_ylabel)
        self.xmin.textEdited.connect(self.update_limits)
        self.xmax.textEdited.connect(self.update_limits)
        self.ymin.textEdited.connect(self.update_limits)
        self.ymax.textEdited.connect(self.update_limits)
        self.set_limits_button.clicked.connect(self.update_limits)

        self.plot_widget.setMenuEnabled(False)

    def create_plot(self, x_var, y_var, x_err, y_err):
        """Create a plot in the widget.

        Create a plot from data in the columns specified by the given column
        names.

        Args:
            x_var: a string containing the name of the column with x values.
            y_var: a string containing the name of the column with y values.
            x_err: a string containing the name of the column with x error
                values.
            y_err: a string containing the name of the column with y error
                values.
        """
        x, y = self.data_model.get_columns([x_var, y_var])
        self.x, self.y = x, y
        if x_err:
            self.x_err = self.data_model.get_column(x_err)
            self.err_width = 2 * self.x_err
        if y_err:
            self.y_err = self.data_model.get_column(y_err)
            self.err_height = 2 * self.y_err
        self.plot = self.plot_widget.plot(
            symbol="o",
            pen=None,
            symbolSize=5,
            symbolPen="k",
            symbolBrush="k",
        )
        self.error_bars = pg.ErrorBarItem()
        self.plot_widget.addItem(self.error_bars)
        self.update_function_label(y_var)
        self.xlabel.setText(x_var)
        self.ylabel.setText(y_var)

        self._y_var = y_var
        self._x_var = x_var

    def update_plot(self):
        """Update plot to reflect any data changes."""
        self.plot.setData(self.x, self.y)
        if self.x_err is not None:
            self.err_width = 2 * self.x_err
        if self.y_err is not None:
            self.err_height = 2 * self.y_err
        self.error_bars.setData(
            x=self.x, y=self.y, width=self.err_width, height=self.err_height
        )
        self.update_limits()

    def update_xlabel(self):
        """Update the x-axis label of the plot."""
        self.plot_widget.setLabel("bottom", self.xlabel.text())
        self.main_window.statusbar.showMessage("Updated label.", msecs=MSG_TIMEOUT)

    def update_ylabel(self):
        """Update the y-axis label of the plot."""
        self.plot_widget.setLabel("left", self.ylabel.text())
        self.main_window.statusbar.showMessage("Updated label.", msecs=MSG_TIMEOUT)

    def update_limits(self):
        """Update the axis limits of the plot."""
        xmin, xmax, ymin, ymax = self.get_adjusted_limits()
        self.plot_widget.setRange(xRange=(xmin, xmax), yRange=(ymin, ymax), padding=0)
        self.main_window.statusbar.showMessage("Updated limits.", msecs=MSG_TIMEOUT)

    def get_adjusted_limits(self):
        """Get adjusted plot limits from the data points and text fields.

        Return the minimum and maximum values of the data points, taking the
        error bars into account and adjust those values using the text fields
        for manual limits in the UI.

        Returns:
            Tuple of four float values (xmin, xmax, ymin, ymax).
        """
        xmin, xmax, ymin, ymax = self.get_limits_from_data()
        xmin = self.update_value_from_text(xmin, self.xmin)
        xmax = self.update_value_from_text(xmax, self.xmax)
        ymin = self.update_value_from_text(ymin, self.ymin)
        ymax = self.update_value_from_text(ymax, self.ymax)
        return xmin, xmax, ymin, ymax

    def get_limits_from_data(self, padding=0.05):
        """Get plot limits from the data points.

        Return the minimum and maximum values of the data points, taking the
        error bars into account.

        Args:
            padding: the relative amount of padding to add to the axis limits.
                Default is .05.

        Returns:
            Tuple of four float values (xmin, xmax, ymin, ymax).
        """
        if self.x_err is not None:
            x_err = self.x_err
        else:
            x_err = 0
        if self.y_err is not None:
            y_err = self.y_err
        else:
            y_err = 0

        xmin = min(self.x - x_err)
        xmax = max(self.x + x_err)
        ymin = min(self.y - y_err)
        ymax = max(self.y + y_err)

        xrange = xmax - xmin
        yrange = ymax - ymin

        xmin -= padding * xrange
        xmax += padding * xrange
        ymin -= padding * yrange
        ymax += padding * yrange

        return xmin, xmax, ymin, ymax

    def update_value_from_text(self, value, widget):
        """Update value from using a widget's text.

        Args:
            value: the original value, if update fails.
            widget: the widget containing the updated value.

        Returns:
            The updated value, or the original value if the update fails.
        """
        try:
            value = float(widget.text())
        except ValueError:
            pass
        return value

    def update_function_label(self, variable):
        """Update function label.

        Updates the text label next to the model function input field. The label
        will contain the name of the dependent variable. For example, "y = ".

        Args:
            variable: a string containing the name of the dependent variable.
        """
        label_text = self.model_func_label.text()
        title, _, _ = label_text.partition(":")
        new_label_text = f"{title}:  {variable} ="
        self.model_func_label.setText(new_label_text)

    def update_fit_params(self):
        """Update fit parameters.

        Gets parameter names from the model function and updates the layout to
        add new parameters and remove parameters which are no longer part of the
        model.
        """
        try:
            params = self.get_params_from_model()
        except (SyntaxError, VariableError) as exc:
            self.main_window.statusbar.showMessage(
                "ERROR: " + str(exc), msecs=MSG_TIMEOUT
            )
            return
        else:
            old_params = set(self._params)
            self.add_params_to_ui(params - old_params)
            self.remove_params_from_ui(old_params - params)
            self.plot_initial_model()
            self.main_window.statusbar.showMessage("Updated model.", msecs=MSG_TIMEOUT)

    def get_params_from_model(self):
        """Get parameter names from the model function.

        Based on the mathematical expression for the model function, determine what are the parameters of the model.

        Raises VariableError when the dependent variable is part of the model function.

        Returns:
            A set of parameter names.
        """
        model_expr = self.model_func.text()
        code = compile(model_expr, "<string>", "eval")
        params = set(code.co_names) - set([self._x_var]) - self._symbols
        if self._y_var in params:
            raise VariableError(
                f"Dependent variable {self._y_var} must not be in function definition"
            )
        else:
            try:
                self.model = models.ExpressionModel(
                    model_expr, independent_vars=[self._x_var]
                )
            except ValueError as exc:
                raise VariableError(exc)
            return params

    def add_params_to_ui(self, params):
        """Add parameters to user interface.

        When the model function is changed and certain parameters are now part
        of the expression, they need to be added to the user interface.

        Args:
            params: a list of parameter names to add to the user interface.
        """
        for p in params:
            layout = QtWidgets.QHBoxLayout()
            layout.addWidget(QtWidgets.QLabel(f"{p}: "))
            min_box = pg.SpinBox(value=-np.inf, finite=False, compactHeight=False)
            min_box.setMaximumWidth(75)
            layout.addWidget(min_box)
            self._idx_min_value_box = layout.count() - 1
            layout.addWidget(QtWidgets.QLabel("≤"))
            value_box = pg.SpinBox(
                value=1.0,
                dec=True,
                step=0.1,
                minStep=0,
                finite=True,
                compactHeight=False,
            )
            value_box.sigValueChanging.connect(self.plot_initial_model)
            value_box.setMaximumWidth(75)
            layout.addWidget(value_box)
            self._idx_value_box = layout.count() - 1
            layout.addWidget(QtWidgets.QLabel("≤"))
            max_box = pg.SpinBox(value=+np.inf, finite=False, compactHeight=False)
            max_box.setMaximumWidth(75)
            layout.addWidget(max_box)
            self._idx_max_value_box = layout.count() - 1
            layout.addWidget(QtWidgets.QCheckBox("Fixed"))
            self._idx_fixed_checkbox = layout.count() - 1

            self._params[p] = layout
            self.param_layout.addLayout(layout)

    def remove_params_from_ui(self, params):
        """Remove parameters from user interface.

        When the model function is changed and certain parameters are no longer
        part of the expression, remove them from the user interface.

        Args:
            params: a list of parameter names to remove from the user interface.
        """
        for p in params:
            layout = self._params[p]
            # delete all widgets from the parameter row
            for _ in range(layout.count()):
                item = layout.takeAt(0)
                item.widget().deleteLater()
            # remove and delete the parameter row
            self.param_layout.removeItem(layout)
            layout.deleteLater()
            # remove the reference to the parameter
            del self._params[p]

    def get_parameter_values(self):
        """Get current parameter values."""
        return {
            k: v.itemAt(self._idx_value_box).widget().value()
            for k, v in self._params.items()
        }

    def get_parameter_hints(self):
        """Get current parameter hints.

        Return not only the current value of parameters, but also the bounds and
        whether to vary the parameter or fix it.

        Returns:
            A dictionary with the parameter names as keys, and a tuple (min,
            value, max, fixed) as values.
        """
        return {
            k: (
                v.itemAt(self._idx_min_value_box).widget().value(),
                v.itemAt(self._idx_value_box).widget().value(),
                v.itemAt(self._idx_max_value_box).widget().value(),
                v.itemAt(self._idx_fixed_checkbox).widget().checkState(),
            )
            for k, v in self._params.items()
        }

    def plot_initial_model(self):
        """Plot model with initial parameters.

        Plots the model with the initial parameters as given in the user
        interface.
        """
        # FIXME Problem for constants like y = a
        x = np.linspace(min(self.x), max(self.x), NUM_POINTS)
        kwargs = self.get_parameter_values()
        kwargs[self._x_var] = x
        y = self.model.eval(**kwargs)

        self._initial_param_plot.setData(x, y)

    def perform_fit(self):
        """Perform fit and plot best fit model.

        Fits the model function to the data to estimate best fit parameters.
        When the fit is successful, the results are given in the result box and
        the best fit is plotted on top of the data.
        """
        param_hints = self.get_parameter_hints()
        for p, (min_, value, max_, is_fixed) in param_hints.items():
            self.model.set_param_hint(
                p, min=min_, value=value, max=max_, vary=not is_fixed
            )

        kwargs = {self._x_var: self.x}
        if self.y_err is not None:
            kwargs["weights"] = 1 / self.y_err
        self.fit = self.model.fit(self.y, **kwargs, nan_policy="omit")
        self.show_fit_results(self.fit)

        x = np.linspace(min(self.x), max(self.x), NUM_POINTS)
        y = self.fit.eval(**{self._x_var: x})
        self._fit_plot.setData(x, y)
        self.main_window.statusbar.showMessage("Updated fit.", msecs=MSG_TIMEOUT)

    def show_fit_results(self, fit):
        """Show the results of the fit in the user interface.

        Args:
            fit: an lmfit.ModelResult object with the result of the fit.
        """
        results = make_header("Fit statistics")
        results += make_table([("# func. eval.", fit.nfev), ("red. chisq", fit.redchi)])

        results += "\n\n"
        results += make_header("Fit parameters")
        results += make_param_table(fit.params)

        self.result_box.setPlainText(results)

    def export_graph(self, filename):
        """Export graph to a file.

        Args:
            filename: path to the file.
        """
        xmin, xmax, ymin, ymax = self.get_adjusted_limits()

        plt.figure()
        plt.errorbar(self.x, self.y, xerr=self.x_err, yerr=self.y_err, fmt="o")
        x = np.linspace(min(self.x), max(self.x), NUM_POINTS)
        y = self.fit.eval(**{self._x_var: x})
        plt.plot(x, y, "r-")
        plt.xlabel(self.xlabel.text())
        plt.ylabel(self.ylabel.text())
        plt.xlim(xmin, xmax)
        plt.ylim(ymin, ymax)
        plt.savefig(filename)


def make_header(text):
    """Make header text with underlined with dashed."""
    return text + "\n" + len(text) * "-" + "\n"


def make_table(data):
    """Format numerical data in a table.

    Calculates the width of the first-column description texts and assumes numerical values for the second column and displays them with precision 4.

    Args:
        data: list of (text, value) tuples.
    """
    width = max([len(u[0]) for u in data])
    text = ""
    fmt = "{:" + str(width) + "s} = {:<9.4g}\n"
    for u, v in data:
        text += fmt.format(u, v)
    return text


def make_param_table(params):
    """Format parameter values in a table.

    Calculates the width of the first column based on parameter names. Formats the parameter values and uncertainties in a general format with precision 4.

    Args:
        params: a lmfit.Parameters object.
    """
    width = max([len(p) for p in params])
    text = ""
    fmt = "{:" + str(width) + "s} = {:< 10.4g} +/- {:< 10.4g}\n"
    for p in params:
        value = params[p].value
        stderr = params[p].stderr
        if stderr is None:
            stderr = 0
        text += fmt.format(p, value, stderr)
    return text