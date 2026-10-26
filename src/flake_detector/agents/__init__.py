"""Agents module for flake-detector."""

from flake_detector.agents.base import Agent
from flake_detector.agents.simulated import SimulatedAgent

__all__ = ["Agent", "SimulatedAgent"]
