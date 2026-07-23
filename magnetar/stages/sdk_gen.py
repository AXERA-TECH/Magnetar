"""SDK-GEN: 生成 Python 和 C++ SDK。"""
import textwrap
from pathlib import Path


def run_mobilenet_python(task_dir: Path, imagenet_labels: list[str]) -> None:
    """生成 MobileNet Python SDK。"""
    py_sdk = task_dir / "sdk" / "python" / "mobilenet_sdk"
    py_sdk.mkdir(parents=True, exist_ok=True)

    (py_sdk / "__init__.py").write_text(
        "from .inference import MobileNetClassifier\n", encoding="utf-8")

    (py_sdk / "inference.py").write_text(textwrap.dedent("""\
        import numpy as np

        DEFAULT_PROVIDER = "AxEngineExecutionProvider"

        class MobileNetClassifier:
            def __init__(self, model_path, providers=None, labels=None):
                import axengine as axe
                self.labels = labels
                preferred = providers or [DEFAULT_PROVIDER]
                try:
                    self.session = axe.InferenceSession(model_path, providers=preferred)
                except Exception:
                    available = list(axe.get_available_providers())
                    fallback = [n for n in available if n not in preferred]
                    if not fallback:
                        raise
                    self.session = axe.InferenceSession(model_path, providers=[fallback[0]])
                self.inputs = self.session.get_inputs()
                self.outputs = self.session.get_outputs()

            def run(self, input_tensor):
                array = np.ascontiguousarray(input_tensor.astype(np.float32))
                return self.session.run(None, {self.inputs[0].name: array})[0]

            def classify(self, input_tensor, k=5):
                from .postprocess import topk
                return topk(self.run(input_tensor), labels=self.labels, k=k)
    """), encoding="utf-8")

    (py_sdk / "example.py").write_text(textwrap.dedent("""\
        import argparse
        import numpy as np
        from pathlib import Path
        from mobilenet_sdk import MobileNetClassifier
        from mobilenet_sdk.postprocess import load_labels

        def main():
            parser = argparse.ArgumentParser()
            parser.add_argument("--model", required=True)
            parser.add_argument("--input", required=True)
            parser.add_argument("--output", required=True)
            parser.add_argument("--labels", default=str(Path(__file__).resolve().parents[1] / "imagenet_classes.txt"))
            parser.add_argument("--topk", type=int, default=5)
            args = parser.parse_args()

            labels = load_labels(args.labels)
            classifier = MobileNetClassifier(args.model, labels=labels)
            input_tensor = np.load(args.input)
            logits = classifier.run(input_tensor)
            np.save(args.output, logits.astype(np.float32))
            for item in classifier.classify(input_tensor, k=args.topk):
                print(f"{item['rank']}: {item['label']} ({item['score']:.6f})")

        if __name__ == "__main__":
            main()
    """), encoding="utf-8")

    (py_sdk / "preprocess.py").write_text(
        "import numpy as np\n\n\ndef preprocess(array):\n    return np.ascontiguousarray(array.astype(np.float32))\n",
        encoding="utf-8")

    (py_sdk / "postprocess.py").write_text(textwrap.dedent("""\
        import numpy as np

        def load_labels(path):
            with open(path, "r", encoding="utf-8") as f:
                return [line.strip() for line in f if line.strip()]

        def topk(logits, labels=None, k=5):
            flat = logits.reshape(-1)
            order = np.argsort(flat)[::-1][:k]
            result = []
            for rank, index in enumerate(order, start=1):
                label = labels[int(index)] if labels and int(index) < len(labels) else str(int(index))
                result.append({"rank": rank, "index": int(index), "label": label, "score": float(flat[index])})
            return result
    """), encoding="utf-8")

    (task_dir / "sdk" / "python" / "imagenet_classes.txt").write_text(
        "\n".join(imagenet_labels) + "\n", encoding="utf-8")
    (task_dir / "sdk" / "python" / "requirements.txt").write_text(
        "numpy\npyaxengine @ git+https://github.com/AXERA-TECH/pyaxengine.git\n", encoding="utf-8")
    (task_dir / "sdk" / "python" / "README.md").write_text(textwrap.dedent("""\
        # Python SDK

        运行环境需要 AX 板端 `/soc/lib` 和 `pyaxengine`。
        默认 provider 为 `AxEngineExecutionProvider`。

        ```bash
        LD_LIBRARY_PATH=/soc/lib PYTHONPATH=$PWD \\
          python3 mobilenet_sdk/example.py --model models/model.axmodel --input input.npy --output output.npy
        ```
    """), encoding="utf-8")


def run_mobilenet_cpp(task_dir: Path, target_hardware: str) -> None:
    """生成 MobileNet C++ SDK。"""
    cpp = task_dir / "sdk" / "cpp"
    cpp.mkdir(parents=True, exist_ok=True)
    (cpp / "include").mkdir(exist_ok=True)
    (cpp / "src").mkdir(exist_ok=True)
    (cpp / "examples").mkdir(exist_ok=True)

    (cpp / "CMakeLists.txt").write_text(textwrap.dedent(f"""\
        cmake_minimum_required(VERSION 3.15)
        project(mobilenet_sdk LANGUAGES CXX C)
        set(CMAKE_CXX_STANDARD 14)
        set(CMAKE_POSITION_INDEPENDENT_CODE ON)

        if(DEFINED CMAKE_TOOLCHAIN_FILE)
            add_compile_options(-mcpu=cortex-a55)
            add_definitions(-DTARGET_AARCH64)
        endif()

        include_directories(include ${{AX_RUNTIME_ROOT}}/include)
        link_directories(${{AX_RUNTIME_ROOT}}/lib)

        add_library(mobilenet_sdk STATIC src/mobilenet_runner.cpp)
        target_link_libraries(mobilenet_sdk ax_engine ax_sys pthread dl atomic)

        add_executable(mobilenet_example examples/main.cpp)
        target_link_libraries(mobilenet_example mobilenet_sdk)
    """), encoding="utf-8")

    (cpp / "include" / "mobilenet_runner.hpp").write_text(textwrap.dedent("""\
        #pragma once
        #include <string>
        #include <vector>
        #include <cstdint>

        class MobileNetRunner {
        public:
            MobileNetRunner(const std::string& model_path);
            ~MobileNetRunner();
            std::vector<float> Run(const float* input, int64_t size);
        private:
            void* engine_ = nullptr;
            void* context_ = nullptr;
        };
    """), encoding="utf-8")

    (cpp / "src" / "mobilenet_runner.cpp").write_text(textwrap.dedent("""\
        #include "mobilenet_runner.hpp"
        #include "ax_engine_api.h"
        #include <cstring>
        #include <stdexcept>

        MobileNetRunner::MobileNetRunner(const std::string& model_path) {
            auto* engine = ax_engine_create();
            if (!engine) throw std::runtime_error("ax_engine_create failed");
            engine_ = engine;

            AX_ENGINE_IO_INFO io_info;
            if (ax_engine_load_model(engine_, model_path.c_str(), &io_info) != 0)
                throw std::runtime_error("ax_engine_load_model failed");

            context_ = ax_engine_create_context(engine_);
            if (!context_) throw std::runtime_error("ax_engine_create_context failed");
        }

        MobileNetRunner::~MobileNetRunner() {
            if (context_) ax_engine_destroy_context(context_);
            if (engine_) ax_engine_destroy(engine_);
        }

        std::vector<float> MobileNetRunner::Run(const float* input, int64_t size) {
            AX_ENGINE_IO_INFO io_info;
            ax_engine_get_io_info(engine_, &io_info);

            AX_ENGINE_IO_BUFFER_T io_buffers[io_info.n_input + io_info.n_output];
            memset(io_buffers, 0, sizeof(io_buffers));

            io_buffers[0].pVir = const_cast<float*>(input);
            io_buffers[0].nSize = size * sizeof(float);

            for (int i = 0; i < io_info.n_output; i++) {
                io_buffers[io_info.n_input + i].pVir = nullptr;
                io_buffers[io_info.n_input + i].nSize = 0;
            }

            if (ax_engine_run_sync(context_, io_info.n_input + io_info.n_output, io_buffers) != 0)
                throw std::runtime_error("ax_engine_run_sync failed");

            int out_idx = io_info.n_input;
            int count = io_buffers[out_idx].nSize / sizeof(float);
            std::vector<float> output(count);
            memcpy(output.data(), io_buffers[out_idx].pVir, io_buffers[out_idx].nSize);
            return output;
        }
    """), encoding="utf-8")

    (cpp / "examples" / "main.cpp").write_text(textwrap.dedent("""\
        #include "mobilenet_runner.hpp"
        #include <fstream>
        #include <iostream>
        #include <vector>
        #include <algorithm>
        #include <cstring>

        int main(int argc, char* argv[]) {
            if (argc < 4) {
                std::cerr << "Usage: " << argv[0]
                          << " <model.axmodel> <input.bin> <output.bin> [labels.txt]" << std::endl;
                return 1;
            }
            const char* model_path = argv[1];
            const char* input_path = argv[2];
            const char* output_path = argv[3];

            MobileNetRunner classifier(model_path);

            std::ifstream input_file(input_path, std::ios::binary);
            input_file.seekg(0, std::ios::end);
            size_t file_size = input_file.tellg();
            input_file.seekg(0, std::ios::beg);
            std::vector<float> input_data(file_size / sizeof(float));
            input_file.read(reinterpret_cast<char*>(input_data.data()), file_size);

            auto output = classifier.Run(input_data.data(), input_data.size());

            std::ofstream out(output_path, std::ios::binary);
            out.write(reinterpret_cast<const char*>(output.data()), output.size() * sizeof(float));

            std::vector<std::pair<float, int>> scored;
            for (size_t i = 0; i < output.size(); i++)
                scored.emplace_back(output[i], i);
            std::sort(scored.rbegin(), scored.rend());

            std::vector<std::string> labels;
            if (argc >= 5) {
                std::ifstream lf(argv[4]);
                std::string line;
                while (std::getline(lf, line))
                    if (!line.empty()) labels.push_back(line);
            }

            for (int k = 0; k < 5 && k < (int)scored.size(); k++) {
                std::string label = labels.empty() || scored[k].second >= (int)labels.size()
                    ? std::to_string(scored[k].second)
                    : labels[scored[k].second];
                std::cout << (k + 1) << ": " << label
                          << " (" << scored[k].first << ")" << std::endl;
            }
            return 0;
        }
    """), encoding="utf-8")

    (cpp / "imagenet_classes.txt").write_text(
        "\n".join(MOBILENET_LABELS) + "\n", encoding="utf-8")

    (task_dir / "sdk" / "cpp" / "README.md").write_text(textwrap.dedent("""\
        # C++ SDK

        交叉编译后在 AX 板端运行。需要 AX runtime 头文件和库。

        ```bash
        cmake -S cpp -B cpp/build-aarch64 \\
          -DCMAKE_TOOLCHAIN_FILE=cpp/toolchain-aarch64.cmake \\
          -DAX_RUNTIME_ROOT=/path/to/ax/runtime
        cmake --build cpp/build-aarch64
        ```

        板端运行：
        ```bash
        LD_LIBRARY_PATH=/soc/lib ./mobilenet_example model.axmodel input.bin output.bin imagenet_classes.txt
        ```
    """), encoding="utf-8")


MOBILENET_LABELS = [
    "tench", "goldfish", "great white shark", "tiger shark", "hammerhead",
    "electric ray", "stingray", "cock", "hen", "ostrich",
    "brambling", "goldfinch", "house finch", "junco", "indigo bunting",
    "robin", "bulbul", "jay", "magpie", "chickadee",
    "water ouzel", "kite", "bald eagle", "vulture", "great grey owl",
    "European fire salamander", "common newt", "eft", "spotted salamander", "axolotl",
    "bullfrog", "tree frog", "tailed frog", "loggerhead", "leatherback turtle",
    "mud turtle", "terrapin", "box turtle", "banded gecko", "common iguana",
    "American chameleon", "whiptail", "agama", "frilled lizard", "alligator lizard",
    "Gila monster", "green lizard", "African chameleon", "Komodo dragon", "African crocodile",
    "American alligator", "triceratops", "thunder snake", "ringneck snake", "hognose snake",
    "green snake", "king snake", "garter snake", "water snake", "vine snake",
    "night snake", "boa constrictor", "rock python", "Indian cobra", "green mamba",
    "sea snake", "horned viper", "diamondback", "sidewinder", "trilobite",
    "harvestman", "scorpion", "black and gold garden spider", "barn spider", "garden spider",
    "black widow", "tarantula", "wolf spider", "tick", "centipede",
    "black grouse", "ptarmigan", "ruffed grouse", "prairie chicken", "peacock",
    "quail", "partridge", "African grey", "macaw", "sulphur-crested cockatoo",
    "lorikeet", "coucal", "bee eater", "hornbill", "hummingbird",
    "jacamar", "toucan", "drake", "red-breasted merganser", "goose",
    "black swan", "tusker", "echidna", "platypus", "wallaby",
    "koala", "wombat", "jellyfish", "sea anemone", "brain coral",
    "flatworm", "nematode", "conch", "snail", "slug",
    "sea slug", "chiton", "chambered nautilus", "Dungeness crab", "rock crab",
    "fiddler crab", "king crab", "American lobster", "spiny lobster", "crayfish",
    "hermit crab", "isopod", "white stork", "black stork", "spoonbill",
    "flamingo", "little blue heron", "American egret", "bittern", "crane",
    "limpkin", "European gallinule", "American coot", "bustard", "ruddy turnstone",
    "red-backed sandpiper", "redshank", "dowitcher", "oystercatcher", "pelican",
    "king penguin", "albatross", "grey whale", "killer whale", "dugong",
    "sea lion", "Chihuahua", "Japanese spaniel", "Maltese dog", "Pekinese",
    "Shih-Tzu", "Blenheim spaniel", "papillon", "toy terrier", "Rhodesian ridgeback",
    "Afghan hound", "basset", "beagle", "bloodhound", "bluetick",
    "black-and-tan coonhound", "Walker hound", "English foxhound", "redbone", "borzoi",
    "Irish wolfhound", "Italian greyhound", "whippet", "Ibizan hound", "Norwegian elkhound",
    "otterhound", "Saluki", "Scottish deerhound", "Weimaraner", "Staffordshire bullterrier",
    "American Staffordshire terrier", "Bedlington terrier", "Border terrier", "Kerry blue terrier", "Irish terrier",
    "Norfolk terrier", "Norwich terrier", "Yorkshire terrier", "wire-haired fox terrier", "Lakeland terrier",
    "Sealyham terrier", "Airedale", "cairn", "Australian terrier", "Dandie Dinmont",
    "Boston bull", "miniature schnauzer", "giant schnauzer", "standard schnauzer", "Scotch terrier",
    "Tibetan terrier", "silky terrier", "soft-coated wheaten terrier", "West Highland white terrier", "Lhasa",
    "flat-coated retriever", "curly-coated retriever", "golden retriever", "Labrador retriever", "Chesapeake Bay retriever",
    "German short-haired pointer", "vizsla", "English setter", "Irish setter", "Gordon setter",
    "Brittany spaniel", "clumber", "English springer", "Welsh springer spaniel", "cocker spaniel",
    "Sussex spaniel", "Irish water spaniel", "kuvasz", "schipperke", "groenendael",
    "malinois", "briard", "kelpie", "komondor", "Old English sheepdog",
    "Shetland sheepdog", "collie", "Border collie", "Bouvier des Flandres", "Rottweiler",
    "German shepherd", "Doberman", "miniature pinscher", "Greater Swiss Mountain dog", "Bernese mountain dog",
    "Appenzeller", "EntleBucher", "boxer", "bull mastiff", "Tibetan mastiff",
    "French bulldog", "Great Dane", "Saint Bernard", "Eskimo dog", "malamute",
    "Siberian husky", "dalmatian", "affenpinscher", "basenji", "pug",
    "Leonberg", "Newfoundland", "Great Pyrenees", "Samoyed", "Pomeranian",
    "chow", "keeshond", "Brabancon griffon", "Pembroke", "Cardigan",
    "toy poodle", "miniature poodle", "standard poodle", "Mexican hairless", "timber wolf",
    "white wolf", "red wolf", "coyote", "dingo", "dhole",
    "African hunting dog", "hyena", "red fox", "kit fox", "Arctic fox",
    "grey fox", "tabby", "tiger cat", "Persian cat", "Siamese cat",
    "Egyptian cat", "cougar", "lynx", "leopard", "snow leopard",
    "jaguar", "lion", "tiger", "cheetah", "brown bear",
    "American black bear", "ice bear", "sloth bear", "mongoose", "meerkat",
    "tiger beetle", "ladybug", "ground beetle", "long-horned beetle", "leaf beetle",
    "dung beetle", "rhinoceros beetle", "weevil", "fly", "bee",
    "ant", "grasshopper", "cricket", "walking stick", "cockroach",
    "mantis", "cicada", "leafhopper", "lacewing", "dragonfly",
    "damselfly", "admiral", "ringlet", "monarch", "cabbage butterfly",
    "sulphur butterfly", "lycaenid", "starfish", "sea urchin", "sea cucumber",
    "wood rabbit", "hare", "Angora", "hamster", "porcupine",
    "fox squirrel", "marmot", "beaver", "guinea pig", "sorrel",
    "zebra", "hog", "wild boar", "warthog", "hippopotamus",
    "ox", "water buffalo", "bison", "ram", "bighorn",
    "ibex", "hartebeest", "impala", "gazelle", "Arabian camel",
    "llama", "weasel", "mink", "polecat", "black-footed ferret",
    "otter", "skunk", "badger", "armadillo", "three-toed sloth",
    "orangutan", "gorilla", "chimpanzee", "gibbon", "siamang",
    "guenon", "patas", "baboon", "macaque", "langur",
    "colobus", "proboscis monkey", "marmoset", "capuchin", "howler monkey",
    "titi", "spider monkey", "squirrel monkey", "Madagascar cat", "indri",
    "Indian elephant", "African elephant", "lesser panda", "giant panda", "barracouta",
    "eel", "coho", "rock beauty", "anemone fish", "sturgeon",
    "gar", "lionfish", "puffer", "abacus", "abaya",
    "academic gown", "accordion", "acoustic guitar", "aircraft carrier", "airliner",
    "airship", "altar", "ambulance", "amphibian", "analog clock",
    "apiary", "apron", "ashcan", "assault rifle", "backpack",
    "bakery", "balance beam", "balloon", "ballpoint", "Band Aid",
    "banjo", "bannister", "barbell", "barber chair", "barbershop",
    "barn", "barometer", "barrel", "barrow", "baseball",
    "basketball", "bassinet", "bassoon", "bathing cap", "bath towel",
    "bathtub", "beach wagon", "beacon", "beaker", "bearskin",
    "beer bottle", "beer glass", "bell cote", "bib", "bicycle-built-for-two",
    "bikini", "binder", "binoculars", "birdhouse", "boathouse",
    "bobsled", "bolo tie", "bonnet", "bookcase", "bookshop",
    "bottlecap", "bow", "bow tie", "brass", "brassiere",
    "breakwater", "breastplate", "broom", "bucket", "buckle",
    "bulletproof vest", "bullet train", "butcher shop", "cab", "caldron",
    "candle", "cannon", "canoe", "can opener", "cardigan",
    "car mirror", "carousel", "carpenter's kit", "carton", "car wheel",
    "cash machine", "cassette", "cassette player", "castle", "catamaran",
    "CD player", "cello", "cellular telephone", "chain", "chainlink fence",
    "chain mail", "chain saw", "chest", "chiffonier", "chime",
    "china cabinet", "Christmas stocking", "church", "cinema", "cleaver",
    "cliff dwelling", "cloak", "clog", "cocktail shaker", "coffee mug",
    "coffeepot", "coil", "combination lock", "computer keyboard", "confectionery",
    "container ship", "convertible", "corkscrew", "cornet", "cowboy boot",
    "cowboy hat", "cradle", "crane", "crash helmet", "crate",
    "crib", "Crock Pot", "croquet ball", "crutch", "cuirass",
    "dam", "desk", "desktop computer", "dial telephone", "diaper",
    "digital clock", "digital watch", "dining table", "dishrag", "dishwasher",
    "disk brake", "dock", "dogsled", "dome", "doormat",
    "drilling platform", "drum", "drumstick", "dumbbell", "Dutch oven",
    "electric fan", "electric guitar", "electric locomotive", "entertainment center", "envelope",
    "espresso maker", "face powder", "feather boa", "file", "fireboat",
    "fire engine", "fire screen", "flagpole", "flute", "folding chair",
    "football helmet", "forklift", "fountain", "fountain pen", "four-poster",
    "freight car", "French horn", "frying pan", "fur coat", "garbage truck",
    "gasmask", "gas pump", "goblet", "go-kart", "golf ball",
    "golfcart", "gondola", "gong", "gown", "grand piano",
    "greenhouse", "grille", "grocery store", "guillotine", "hair slide",
    "hair spray", "half track", "hammer", "hamper", "hand blower",
    "hand-held computer", "handkerchief", "hard disc", "harmonica", "harp",
    "harvester", "hatchet", "holster", "home theater", "honeycomb",
    "hook", "hoopskirt", "horizontal bar", "horse cart", "hourglass",
    "iPod", "iron", "jack-o'-lantern", "jean", "jeep",
    "jersey", "jigsaw puzzle", "jinrikisha", "joystick", "kimono",
    "knee pad", "knot", "lab coat", "ladle", "lampshade",
    "laptop", "lawn mower", "lens cap", "letter opener", "library",
    "lifeboat", "lighter", "limousine", "liner", "lipstick",
    "Loafer", "lotion", "loudspeaker", "loupe", "lumbermill",
    "magnetic compass", "mailbag", "mailbox", "maillot", "maillot",
    "manhole cover", "maraca", "marimba", "mask", "matchstick",
    "maypole", "maze", "measuring cup", "medicine chest", "megalith",
    "microphone", "microwave", "military uniform", "milk can", "minibus",
    "miniskirt", "minivan", "missile", "mitten", "mixing bowl",
    "mobile home", "Model T", "modem", "monastery", "monitor",
    "moped", "mortar", "mortarboard", "mosque", "mosquito net",
    "motor scooter", "mountain bike", "mountain tent", "mouse", "mousetrap",
    "moving van", "muzzle", "nail", "neck brace", "necklace",
    "nipple", "notebook", "obelisk", "oboe", "ocarina",
    "odometer", "oil filter", "organ", "oscilloscope", "overskirt",
    "oxcart", "oxygen mask", "packet", "paddle", "paddlewheel",
    "padlock", "paintbrush", "pajama", "palace", "panpipe",
    "paper towel", "parachute", "parallel bars", "park bench", "parking meter",
    "passenger car", "patio", "pay-phone", "pedestal", "pencil box",
    "pencil sharpener", "perfume", "Petri dish", "photocopier", "pick",
    "pickelhaube", "picket fence", "pickup", "pier", "piggy bank",
    "pill bottle", "pillow", "ping-pong ball", "pinwheel", "pirate",
    "pitcher", "plane", "planetarium", "plastic bag", "plate rack",
    "plow", "plunger", "Polaroid camera", "pole", "police van",
    "poncho", "pool table", "pop bottle", "pot", "potter's wheel",
    "power drill", "prayer rug", "printer", "prison", "projectile",
    "projector", "puck", "punching bag", "purse", "quill",
    "quilt", "racer", "racket", "radiator", "radio",
    "radio telescope", "rain barrel", "recreational vehicle", "reel", "reflex camera",
    "refrigerator", "remote control", "restaurant", "revolver", "rifle",
    "rocking chair", "rotisserie", "rubber eraser", "rugby ball", "rule",
    "running shoe", "safe", "safety pin", "saltshaker", "sandal",
    "sarong", "sax", "scabbard", "scale", "school bus",
    "schooner", "scoreboard", "screen", "screw", "screwdriver",
    "seat belt", "sewing machine", "shield", "shoe shop", "shoji",
    "shopping basket", "shopping cart", "shovel", "shower cap", "shower curtain",
    "ski", "ski mask", "sleeping bag", "slide rule", "sliding door",
    "slot", "snorkel", "snowmobile", "snowplow", "soap dispenser",
    "soccer ball", "sock", "solar dish", "sombrero", "soup bowl",
    "space bar", "space heater", "space shuttle", "spatula", "speedboat",
    "spider web", "spindle", "sports car", "spotlight", "stage",
    "steam locomotive", "steel arch bridge", "steel drum", "stethoscope", "stole",
    "stone wall", "stopwatch", "stove", "strainer", "streetcar",
    "stretcher", "studio couch", "stupa", "submarine", "suit",
    "sundial", "sunglass", "sunglasses", "sunscreen", "suspension bridge",
    "swab", "sweatshirt", "swimming trunks", "swing", "switch",
    "syringe", "table lamp", "tank", "tape player", "teapot",
    "teddy", "television", "tennis ball", "thatch", "theater curtain",
    "thimble", "thresher", "throne", "tile roof", "toaster",
    "tobacco shop", "toilet seat", "torch", "totem pole", "tow truck",
    "toyshop", "tractor", "trailer truck", "tray", "trench coat",
    "tricycle", "trimaran", "tripod", "triumphal arch", "trolleybus",
    "trombone", "tub", "turnstile", "typewriter keyboard", "umbrella",
    "unicycle", "upright", "vacuum", "vase", "vault",
    "velvet", "vending machine", "vestment", "viaduct", "violin",
    "volleyball", "waffle iron", "wall clock", "wallet", "wardrobe",
    "warplane", "washbasin", "washer", "water bottle", "water jug",
    "water tower", "whiskey jug", "whistle", "wig", "window screen",
    "window shade", "Windsor tie", "wine bottle", "wing", "wok",
    "wooden spoon", "wool", "worm fence", "wreck", "yawl",
    "yurt", "web site", "comic book", "crossword puzzle", "street sign",
    "traffic light", "book jacket", "menu", "plate", "guacamole",
    "consomme", "hot pot", "trifle", "ice cream", "ice lolly",
    "French loaf", "bagel", "pretzel", "cheeseburger", "hotdog",
    "mashed potato", "head cabbage", "broccoli", "cauliflower", "zucchini",
    "spaghetti squash", "acorn squash", "butternut squash", "cucumber", "artichoke",
    "bell pepper", "cardoon", "mushroom", "Granny Smith", "strawberry",
    "orange", "lemon", "fig", "pineapple", "banana",
    "jackfruit", "custard apple", "pomegranate", "hay", "carbonara",
    "chocolate sauce", "dough", "meat loaf", "pizza", "potpie",
    "burrito", "red wine", "espresso", "cup", "eggnog",
    "alp", "bubble", "cliff", "coral reef", "geyser",
    "lakeside", "promontory", "sandbar", "seashore", "valley",
    "volcano", "ballplayer", "groom", "scuba diver", "rapeseed",
    "daisy", "yellow lady's slipper", "corn", "acorn", "hip",
    "buckeye", "coral fungus", "agaric", "gyromitra", "stinkhorn",
    "earthstar", "hen-of-the-woods", "bolete", "ear", "toilet tissue",
]
