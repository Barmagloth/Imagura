"""Tests for LoadTask priority ordering from imagura/types.py."""

from __future__ import annotations
import pytest
import time
from imagura.types import LoadTask, LoadPriority


def dummy_callback():
    """Dummy callback for LoadTask."""
    pass


class TestLoadTaskPriority:
    """Test LoadTask priority ordering."""

    def test_current_beats_neighbor(self):
        """Test CURRENT priority beats NEIGHBOR priority."""
        task_current = LoadTask("path1", LoadPriority.CURRENT, dummy_callback, 1.0)
        task_neighbor = LoadTask("path2", LoadPriority.NEIGHBOR, dummy_callback, 1.0)

        assert task_current < task_neighbor

    def test_neighbor_beats_gallery(self):
        """Test NEIGHBOR priority beats GALLERY priority."""
        task_neighbor = LoadTask("path1", LoadPriority.NEIGHBOR, dummy_callback, 1.0)
        task_gallery = LoadTask("path2", LoadPriority.GALLERY, dummy_callback, 1.0)

        assert task_neighbor < task_gallery

    def test_current_beats_gallery(self):
        """Test CURRENT priority beats GALLERY priority."""
        task_current = LoadTask("path1", LoadPriority.CURRENT, dummy_callback, 1.0)
        task_gallery = LoadTask("path2", LoadPriority.GALLERY, dummy_callback, 1.0)

        assert task_current < task_gallery

    def test_fifo_within_priority(self):
        """Test FIFO ordering (earlier timestamp wins) within same priority."""
        earlier_time = 100.0
        later_time = 200.0

        task_earlier = LoadTask("path1", LoadPriority.NEIGHBOR, dummy_callback, earlier_time)
        task_later = LoadTask("path2", LoadPriority.NEIGHBOR, dummy_callback, later_time)

        assert task_earlier < task_later

    def test_same_priority_same_timestamp(self):
        """Test equal tasks are not less than each other."""
        task1 = LoadTask("path1", LoadPriority.NEIGHBOR, dummy_callback, 150.0)
        task2 = LoadTask("path2", LoadPriority.NEIGHBOR, dummy_callback, 150.0)

        assert not (task1 < task2)
        assert not (task2 < task1)

    def test_priority_ordering_values(self):
        """Test priority enum values are ordered correctly."""
        assert LoadPriority.CURRENT < LoadPriority.NEIGHBOR
        assert LoadPriority.NEIGHBOR < LoadPriority.GALLERY

    def test_sort_mixed_priorities_and_timestamps(self):
        """Test sorting a list of mixed priority/timestamp tasks."""
        tasks = [
            LoadTask("a", LoadPriority.GALLERY, dummy_callback, 300.0),
            LoadTask("b", LoadPriority.CURRENT, dummy_callback, 200.0),
            LoadTask("c", LoadPriority.NEIGHBOR, dummy_callback, 100.0),
            LoadTask("d", LoadPriority.CURRENT, dummy_callback, 100.0),
            LoadTask("e", LoadPriority.NEIGHBOR, dummy_callback, 200.0),
        ]

        sorted_tasks = sorted(tasks)

        # First should be both CURRENT tasks, earlier timestamp first
        assert sorted_tasks[0].priority == LoadPriority.CURRENT
        assert sorted_tasks[0].timestamp == 100.0
        assert sorted_tasks[1].priority == LoadPriority.CURRENT
        assert sorted_tasks[1].timestamp == 200.0

        # Then NEIGHBOR tasks
        assert sorted_tasks[2].priority == LoadPriority.NEIGHBOR
        assert sorted_tasks[2].timestamp == 100.0
        assert sorted_tasks[3].priority == LoadPriority.NEIGHBOR
        assert sorted_tasks[3].timestamp == 200.0

        # Finally GALLERY
        assert sorted_tasks[4].priority == LoadPriority.GALLERY

    def test_loadtask_creation(self):
        """Test creating LoadTask instances with various parameters."""
        task = LoadTask(
            path="test.jpg",
            priority=LoadPriority.CURRENT,
            callback=dummy_callback,
            timestamp=123.45,
        )

        assert task.path == "test.jpg"
        assert task.priority == LoadPriority.CURRENT
        assert task.callback == dummy_callback
        assert task.timestamp == 123.45

    def test_loadtask_default_timestamp(self):
        """Test LoadTask default timestamp is 0.0."""
        task = LoadTask("test.jpg", LoadPriority.GALLERY, dummy_callback)
        assert task.timestamp == 0.0
