"""
Word lists for generating friendly, memorable session slugs.
Privacy: slugs are not linked to any participant or facilitator identity.
"""
import random

_ADJECTIVES = [
    "amber", "azure", "bright", "calm", "cedar", "clear", "coral", "crisp",
    "deep", "early", "ember", "fern", "flint", "foggy", "forest", "frost",
    "gentle", "golden", "hazel", "hollow", "indigo", "jade", "jasper",
    "lake", "lemon", "light", "lime", "linen", "lunar", "maple", "misty",
    "mossy", "north", "opal", "pale", "peach", "pine", "plum", "quiet",
    "rainy", "rapid", "rocky", "rosy", "rust", "sage", "sandy", "silver",
    "slate", "slow", "snowy", "soft", "south", "stark", "steel", "stone",
    "sunny", "swift", "teal", "thorn", "tidal", "timber", "topaz", "upper",
    "violet", "warm", "white", "wild", "winter", "woven", "yellow",
]

_NOUNS = [
    "acorn", "arch", "ash", "bay", "beach", "bear", "birch", "bloom",
    "boat", "brook", "brush", "cliff", "cloud", "coast", "crane", "creek",
    "crow", "deer", "delta", "dove", "duck", "dune", "eagle", "elm",
    "fern", "finch", "fjord", "flame", "fox", "gale", "glen", "gull",
    "hawk", "heath", "heron", "hill", "holly", "inlet", "iris", "isle",
    "ivy", "junco", "kelp", "kite", "knoll", "lake", "lark", "leaf",
    "ledge", "lily", "loon", "lynx", "marsh", "meadow", "mink", "moon",
    "moor", "moss", "moth", "newt", "oak", "orca", "otter", "owl",
    "pebble", "pine", "pond", "pool", "quail", "raven", "reed", "ridge",
    "river", "robin", "rock", "root", "rush", "sage", "salt", "sand",
    "seal", "shell", "shore", "slope", "sparrow", "spruce", "stone",
    "stream", "swan", "swift", "thorn", "thrush", "tide", "timber",
    "toad", "trail", "trout", "vale", "vine", "vole", "wave", "wren",
]


def generate_slug(word_count: int = 4) -> str:
    """Generate a random friendly slug from the word lists."""
    pool = _ADJECTIVES + _NOUNS
    words = random.sample(pool, word_count)
    return "-".join(words)
