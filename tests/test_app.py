import numpy as np
import pytest
from PySide6 import QtCore, QtWidgets
from pytest_mock import MockerFixture

from tailor.app import Application
from tailor.data_sheet import DataSheet
from tailor.plot_tab import DRAW_CURVE_OPTIONS, DrawCurve, PlotTab


@pytest.fixture()
def data_sheet(mocker: MockerFixture) -> DataSheet:
    sheet = DataSheet(name="Sheet2", id=1234, main_window=mocker.MagicMock())
    sheet.model.setDataFromArray(
        sheet.model.createIndex(0, 0),
        np.array(
            [[0.0, 1.0, 2.0, 3.0, 4.0, 5.0], [float("nan"), 1.0, 4.0, 9.0, 16.0, 25.0]]
        ).T,
    )
    sheet.model.insertCalculatedColumn(2)
    sheet.model.insertCalculatedColumn(3)
    sheet.model.insertCalculatedColumn(4)
    sheet.model.insertCalculatedColumn(5)
    sheet.model.insertCalculatedColumn(6)
    sheet.model.renameColumn(0, "x")
    sheet.model.renameColumn(1, "y")
    sheet.model.renameColumn(2, "z")
    sheet.model.renameColumn(3, "yerr")
    sheet.model.renameColumn(4, "empty")
    sheet.model.renameColumn(5, "position")
    sheet.model.renameColumn(6, "use_pos")
    sheet.model.updateColumnExpression(2, "0.02 * x ** 2")
    sheet.model.updateColumnExpression(3, "0.1")
    sheet.model.updateColumnExpression(5, "0.5 * x ** 2 + y * z")
    sheet.model.updateColumnExpression(6, "position")
    return sheet


@pytest.fixture()
def plot_tab(data_sheet: DataSheet, mocker: MockerFixture) -> PlotTab:
    plot_tab = PlotTab(
        name="Plot 1",
        id=12345,
        data_sheet=data_sheet,
        x_col="col1",
        y_col="col2",
        x_err_col="col3",
        y_err_col="col4",
    )
    plot_tab.model.x_label = "Time"
    plot_tab.model.y_label = "Distance"
    plot_tab.model.update_model_expression("a * x + b")
    plot_tab.model._parameters["a"].value = 2.0
    plot_tab.model.perform_fit()
    option = DrawCurve.ON_DOMAIN
    option_idx = list(DRAW_CURVE_OPTIONS.keys()).index(option)
    plot_tab.ui.draw_curve_option.setCurrentIndex(option_idx)
    return plot_tab


@pytest.fixture()
def simple_project_without_plot(data_sheet: DataSheet) -> Application:
    app = Application(add_sheet=True)
    app.ui.tabWidget.addTab(data_sheet, data_sheet.name)
    return app


@pytest.fixture()
def simple_project(
    simple_project_without_plot: Application, plot_tab: PlotTab
) -> Application:
    simple_project_without_plot.ui.tabWidget.addTab(plot_tab, plot_tab.name)
    return simple_project_without_plot


class TestSheets:
    def test_simple_project_without_plot_with_plot(
        self, simple_project: Application
    ) -> None:
        tabs = [
            simple_project.ui.tabWidget.widget(idx)
            for idx in range(simple_project.ui.tabWidget.count())
        ]

        assert len(tabs) == 3
        assert isinstance(tabs[0], DataSheet)
        assert isinstance(tabs[1], DataSheet)
        assert isinstance(tabs[2], PlotTab)

    @pytest.mark.skip("shows GUI")
    def test_show_simple_project(self, simple_project: Application) -> None:
        qapp = QtWidgets.QApplication.instance()
        simple_project.show()
        qapp.exec()

    def test_close_sheet_without_any_plots(
        self, simple_project_without_plot: Application, mocker: MockerFixture
    ) -> None:
        mocker.patch.object(simple_project_without_plot, "confirm_close_dialog")

        simple_project_without_plot.confirm_close_dialog.return_value = False
        assert simple_project_without_plot.ui.tabWidget.count() == 2
        simple_project_without_plot.close_tab(1)
        assert simple_project_without_plot.ui.tabWidget.count() == 2

        simple_project_without_plot.confirm_close_dialog.return_value = True
        simple_project_without_plot.close_tab(1)
        assert simple_project_without_plot.ui.tabWidget.count() == 1
        sheet: DataSheet = simple_project_without_plot.ui.tabWidget.widget(0)
        assert sheet.name == "Sheet1"

    def test_close_plot(
        self, simple_project: Application, mocker: MockerFixture
    ) -> None:
        mocker.patch.object(simple_project, "confirm_close_dialog")

        # check that tab under test is indeed a plot
        PLOT_IDX = 2
        assert isinstance(simple_project.ui.tabWidget.widget(PLOT_IDX), PlotTab)

        # cancel close request
        simple_project.confirm_close_dialog.return_value = False
        assert simple_project.ui.tabWidget.count() == 3
        simple_project.close_tab(PLOT_IDX)
        assert simple_project.ui.tabWidget.count() == 3

        # confirm close request
        simple_project.confirm_close_dialog.return_value = True
        simple_project.close_tab(PLOT_IDX)
        assert simple_project.ui.tabWidget.count() == 2
        for idx in range(2):
            widget = simple_project.ui.tabWidget.widget(idx)
            assert isinstance(widget, DataSheet)

    def test_close_sheet_with_no_plots(
        self, simple_project: Application, mocker: MockerFixture
    ) -> None:
        mocker.patch.object(simple_project, "confirm_close_dialog")
        simple_project.confirm_close_dialog.return_value = True

        simple_project.close_tab(0)

        assert simple_project.ui.tabWidget.count() == 2
        assert simple_project.ui.tabWidget.widget(0).name == "Sheet2"

    def test_close_sheet_with_associated_plots(
        self, simple_project: Application, mocker: MockerFixture
    ) -> None:
        mocker.patch.object(simple_project, "confirm_close_dialog")
        simple_project.confirm_close_dialog.return_value = True

        # tab 1 (Sheet2) has one associated plot in tab 2
        simple_project.close_tab(1)

        assert simple_project.ui.tabWidget.count() == 1
        assert simple_project.ui.tabWidget.widget(0).name == "Sheet1"

    def test_close_sheet_lists_associated_plots(
        self, simple_project: Application, mocker: MockerFixture
    ) -> None:
        mocker.patch.object(simple_project, "confirm_close_dialog")
        simple_project.confirm_close_dialog.return_value = False

        # no associated plots
        simple_project.close_tab(0)
        assert "Plot 1" not in simple_project.confirm_close_dialog.call_args.args[0]

        # associated plots: Plot 1
        simple_project.close_tab(1)
        assert "Plot 1" in simple_project.confirm_close_dialog.call_args.args[0]

    def test_close_last_remaining_tabs_starts_new_project(
        self, simple_project: Application, mocker: MockerFixture
    ) -> None:
        mocker.patch.object(simple_project, "confirm_close_dialog")
        mocker.patch.object(simple_project, "clear_all")
        simple_project.confirm_close_dialog.return_value = True

        # close Sheet1
        simple_project.close_tab(0)
        # close Sheet2; should also close Plot1 and start new project
        simple_project.close_tab(0)

        simple_project.clear_all.assert_called_with(add_sheet=True)

    def test_remove_unused_column(
        self, simple_project: Application, mocker: MockerFixture
    ) -> None:
        mocker.patch.object(simple_project, "show_warning_dialog")
        simple_project.ui.tabWidget.setCurrentIndex(1)
        sheet: DataSheet = simple_project.ui.tabWidget.currentWidget()
        mocker.patch.object(sheet, "remove_selected_columns")

        # no associated plots or columns, confirmation not needed
        sheet.ui.data_view.selectColumn(4)
        simple_project.remove_selected_columns()
        simple_project.show_warning_dialog.assert_not_called()
        sheet.remove_selected_columns.assert_called()

    def test_remove_used_column_lists_associated_plots(
        self, simple_project: Application, mocker: MockerFixture
    ) -> None:
        mocker.patch.object(simple_project, "show_warning_dialog")
        simple_project.ui.tabWidget.setCurrentIndex(1)
        sheet: DataSheet = simple_project.ui.tabWidget.currentWidget()
        mocker.patch.object(sheet, "remove_selected_columns")

        # associated plots: Plot 1
        sheet.ui.data_view.selectColumn(0)
        simple_project.remove_selected_columns()
        simple_project.show_warning_dialog.assert_called()
        assert "Plot 1" in simple_project.show_warning_dialog.call_args.args[0]
        sheet.remove_selected_columns.assert_not_called()

    def test_remove_used_column_lists_associated_calculated_columns(
        self, simple_project: Application, mocker: MockerFixture
    ) -> None:
        mocker.patch.object(simple_project, "show_warning_dialog")
        simple_project.ui.tabWidget.setCurrentIndex(1)
        sheet: DataSheet = simple_project.ui.tabWidget.currentWidget()
        mocker.patch.object(sheet, "remove_selected_columns")

        # associated plots: Plot 1
        sheet.ui.data_view.selectColumn(0)
        simple_project.remove_selected_columns()
        simple_project.show_warning_dialog.assert_called()
        assert "'z', 'position'" in simple_project.show_warning_dialog.call_args.args[0]
        assert "empty" not in simple_project.show_warning_dialog.call_args.args[0]
        assert "yerr" not in simple_project.show_warning_dialog.call_args.args[0]
        sheet.remove_selected_columns.assert_not_called()

    def test_remove_column_and_used_column(
        self, simple_project: Application, mocker: MockerFixture
    ) -> None:
        mocker.patch.object(simple_project, "show_warning_dialog")
        simple_project.ui.tabWidget.setCurrentIndex(1)
        sheet: DataSheet = simple_project.ui.tabWidget.currentWidget()
        mocker.patch.object(sheet, "remove_selected_columns")

        # column 'position' is only used by 'use_pos', delete both
        sheet.ui.data_view.selectColumn(5)
        sheet.selection.select(
            sheet.model.index(0, 6),
            QtCore.QItemSelectionModel.Select | QtCore.QItemSelectionModel.Columns,
        )
        simple_project.remove_selected_columns()

        simple_project.show_warning_dialog.assert_not_called()
        sheet.remove_selected_columns.assert_called()
