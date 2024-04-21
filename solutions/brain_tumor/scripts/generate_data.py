import argparse
import numpy as np
import os
import random
import torch as th

from imageprep.export import HDF5Exporter
from imageprep.finder import BRATS2020DataFinder
from imageprep.pipeline import (
    NIfTIImagesLoader,
    ApplyOnImages,
    MeanOfImages,
    NormalizeImages,
    CenterOfMassSplit,
    Rescale,
    StackImages,
    Simulate,
    Reply,
    TakeCentre,
)

from phynn.pde import PDEEval, PDEStaticParams, FisherKolmogorovPDE


def get_args():
    parser = argparse.ArgumentParser(description="Preprocess brain tumor images.")

    parser.add_argument("dataset_path", type=str, help="Path to the dataset directory")
    parser.add_argument("target_path", type=str, help="Path to the target directory")

    parser.add_argument(
        "--target_size",
        type=int,
        default=128,
        required=False,
        help="Target length and width of images after preprocessing",
    )
    parser.add_argument(
        "--simulation_steps",
        type=int,
        default=5,
        required=False,
        help="Simulation steps",
    )

    return parser.parse_args()


def generate(
    dataset_path: os.PathLike,
    target_path: os.PathLike,
    target_size: int,
    simulation_steps: int,
) -> None:
    image_type_weights = {
        "t1": 0.0,
        "t2": 0.0,
        "seg": 0.8,
        "flair": 0.2,
        "t1ce": 0.0,
    }

    pde = FisherKolmogorovPDE()
    params_provider = PDEStaticParams(0, 0)
    pde_eval = PDEEval(
        pde,
        params_provider,
        min_concentration=0.3,
        boundary_condition=lambda x: x > 0.02,
    )

    def transpose(x: np.ndarray) -> np.ndarray:
        return x.transpose((2, 1, 0))

    def random_time_diff() -> int:
        return random.randint(2, 5)

    def random_params() -> tuple[float, ...]:
        return (random.uniform(0.75, 2.0), random.uniform(0.5, 5.0))

    def simulate(x: np.ndarray, t: int, params: tuple[float, ...]) -> np.ndarray:
        with th.no_grad():
            params_provider.values = params
            result = pde_eval(th.tensor(x).unsqueeze(0), th.tensor(t).unsqueeze(0))
            return result.cpu().detach().numpy().squeeze(0)

    finder = BRATS2020DataFinder(dataset_path, list(image_type_weights.keys()))

    loader = NIfTIImagesLoader(finder)
    target_view = ApplyOnImages(loader, transpose)

    centred = TakeCentre(
        target_view, 0, 256
    )  # TODO : find images shapes, centre all dims

    rescaled_0 = Rescale(centred, 0, target_size)
    rescaled_1 = Rescale(rescaled_0, 1, target_size)
    rescaled_2 = Rescale(rescaled_1, 2, target_size)
    normalized = NormalizeImages(rescaled_2)

    mean = MeanOfImages(normalized, image_type_weights)
    mean_normalized = NormalizeImages(mean)

    centre_of_mass_crosses = CenterOfMassSplit(mean_normalized, 0)
    replied = Reply(centre_of_mass_crosses, 2, True)

    simulation = Simulate(
        replied, simulate, random_time_diff, random_params, simulation_steps
    )

    stacked_to_time_series = StackImages(simulation)
    stacked_to_one = StackImages(stacked_to_time_series)

    image = next(stacked_to_one.run()).image
    time = simulation.times
    params = simulation.params

    exporter = HDF5Exporter()
    exporter.export(target_path, image, time, time_series_params=params)


def main():
    args = get_args()
    generate(
        args.dataset_path, args.target_path, args.target_size, args.simulation_steps
    )


if __name__ == "__main__":
    main()