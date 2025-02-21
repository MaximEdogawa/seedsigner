import math

from embit import bip32
from embit.networks import NETWORKS
from binascii import b2a_base64, hexlify
from dataclasses import dataclass
from typing import List
from embit import bip32
from embit.networks import NETWORKS
from embit.psbt import PSBT
from seedener.helpers.ur2.ur_encoder import UREncoder
from seedener.helpers.ur2.ur import UR
from seedener.helpers.qr import QR
from seedener.models import Seed, QRType

from urtypes.crypto import PSBT as UR_PSBT
from urtypes.crypto import Account, HDKey, Output, Keypath, PathComponent, SCRIPT_EXPRESSION_TAG_MAP

from seedener.models.settings import SettingsConstants



@dataclass
class EncodeQR:
    """
       Encode psbt for displaying as qr image
    """
    # TODO: Refactor so that this is a base class with implementation classes for each
    # QR type. No reason exterior code can't directly instantiate the encoder it needs.

    # Dataclass input vars on __init__()
    psbt: PSBT = None
    seed_phrase: List[str] = None
    passphrase: str = None
    derivation: str = None
    network: str = SettingsConstants.MAINNET
    qr_type: str = None
    qr_density: str = SettingsConstants.DENSITY__MEDIUM
    wordlist_language_code: str = SettingsConstants.WORDLIST_LANGUAGE__ENGLISH
    chia_address: str = None

    def __post_init__(self):
        self.qr = QR()

        if not self.qr_type:
            raise Exception('qr_type is required')

        if self.qr_density == None:
            self.qr_density = SettingsConstants.DENSITY__MEDIUM

        self.encoder: BaseQrEncoder = None

        # PSBT formats
        if self.qr_type == QRType.PSBT__SPECTER:
            self.encoder = SpecterPsbtQrEncoder(psbt=self.psbt, qr_density=self.qr_density)

        elif self.qr_type == QRType.PSBT__UR2:
            self.encoder = UrPsbtQrEncoder(psbt=self.psbt, qr_density=self.qr_density)

        # XPUB formats
        elif self.qr_type == QRType.XPUB:
            self.encoder = XpubQrEncoder(
                seed_phrase=self.seed_phrase,
                passphrase=self.passphrase,
                derivation=self.derivation,
                network=self.network,
                wordlist_language_code=self.wordlist_language_code
            )

        elif self.qr_type == QRType.XPUB__UR:
            self.encoder = UrXpubQrEncoder(
                qr_density=self.qr_density,
                seed_phrase=self.seed_phrase,
                passphrase=self.passphrase,
                derivation=self.derivation,
                network=self.network,
                wordlist_language_code=self.wordlist_language_code
            )

        elif self.qr_type == QRType.XPUB__SPECTER:
            self.encoder = SpecterXPubQrEncoder(
                qr_density=self.qr_density,
                seed_phrase=self.seed_phrase,
                passphrase=self.passphrase,
                derivation=self.derivation,
                network=self.network,
                wordlist_language_code=self.wordlist_language_code
            )


        # SeedQR formats
        elif self.qr_type == QRType.SEED__SEEDQR:
            self.encoder = SeedQrEncoder(seed_phrase=self.seed_phrase,
                                         wordlist_language_code=self.wordlist_language_code)

        elif self.qr_type == QRType.SEED__COMPACTSEEDQR:
            self.encoder = CompactSeedQrEncoder(seed_phrase=self.seed_phrase,
                                                wordlist_language_code=self.wordlist_language_code)
        
        elif self.qr_type == QRType.CHIA_ADDRESS:
            self.encoder = ChiaAddressEncoder(address=self.chia_address)

        else:
            raise Exception('QR Type not supported')


    def total_parts(self) -> int:
        return self.encoder.seq_len()


    def next_part(self):
        return self.encoder.next_part()


    def part_to_image(self, part, width=240, height=240, border=3):
        return self.qr.qrimage_io(part, width, height, border)


    def next_part_image(self, width=240, height=240, border=3, background_color="bdbdbd"):
        part = self.next_part()
        if self.qr_type == QRType.SEED__SEEDQR:
            return self.qr.qrimage(part, width, height, border)
        else:
            return self.qr.qrimage_io(part, width, height, border, background_color=background_color)


    # TODO: Make these properties?
    def is_complete(self):
        return self.encoder.is_complete


    def get_qr_density(self):
        return self.qr_density


    def get_qr_type(self):
        return self.qr_type



class BaseQrEncoder:
    def seq_len(self):
        raise Exception("Not implemented in child class")

    def next_part(self) -> str:
        raise Exception("Not implemented in child class")

    @property
    def is_complete(self):
        raise Exception("Not implemented in child class")

    def _create_parts(self):
        raise Exception("Not implemented in child class")



class BasePsbtQrEncoder(BaseQrEncoder):
    def __init__(self, psbt: PSBT):
        self.psbt = psbt



class UrPsbtQrEncoder(BasePsbtQrEncoder):
    def __init__(self, psbt, qr_density):
        super().__init__(psbt)
        self.qr_max_fragment_size = 20
        
        qr_ur_bytes = UR("crypto-psbt", UR_PSBT(self.psbt.serialize()).to_cbor())

        if qr_density == SettingsConstants.DENSITY__LOW:
            self.qr_max_fragment_size = 10
        elif qr_density == SettingsConstants.DENSITY__MEDIUM:
            self.qr_max_fragment_size = 30
        elif qr_density == SettingsConstants.DENSITY__HIGH:
            self.qr_max_fragment_size = 120

        self.ur2_encode = UREncoder(ur=qr_ur_bytes, max_fragment_len=self.qr_max_fragment_size)


    def seq_len(self):
        return self.ur2_encode.fountain_encoder.seq_len()


    def next_part(self) -> str:
        return self.ur2_encode.next_part().upper()


    @property
    def is_complete(self):
        return self.ur2_encode.is_complete()



class SpecterPsbtQrEncoder(BasePsbtQrEncoder):
    def __init__(self, psbt, qr_density):
        super().__init__(psbt)
        self.qr_max_fragement_size = 65
        self.parts = []
        self.part_num_sent = 0
        self.sent_complete = False

        if qr_density == SettingsConstants.DENSITY__LOW:
            self.qr_max_fragement_size = 40
        elif qr_density == SettingsConstants.DENSITY__MEDIUM:
            self.qr_max_fragement_size = 65
        elif qr_density == SettingsConstants.DENSITY__HIGH:
            self.qr_max_fragement_size = 90

        self._create_parts()


    def _create_parts(self):
        base64_psbt = b2a_base64(self.psbt.serialize())

        if base64_psbt[-1:] == b"\n":
            base64_psbt = base64_psbt[:-1]

        base64_psbt = base64_psbt.decode('utf-8')

        start = 0
        stop = self.qr_max_fragement_size
        qr_cnt = ((len(base64_psbt)-1) // self.qr_max_fragement_size) + 1

        if qr_cnt == 1:
            self.parts.append(base64_psbt[start:stop])

        cnt = 0
        while cnt < qr_cnt and qr_cnt != 1:
            part = "p" + str(cnt+1) + "of" + str(qr_cnt) + " " + base64_psbt[start:stop]
            self.parts.append(part)

            start = start + self.qr_max_fragement_size
            stop = stop + self.qr_max_fragement_size
            if stop > len(base64_psbt):
                stop = len(base64_psbt)
            cnt += 1


    def seq_len(self):
        return len(self.parts)


    def next_part(self) -> str:
        # if part num sent is gt number of parts, start at 0
        if self.part_num_sent > (len(self.parts) - 1):
            self.part_num_sent = 0

        part = self.parts[self.part_num_sent]

        # when parts sent eq num of parts in list
        if self.part_num_sent == (len(self.parts) - 1):
            self.sent_complete = True

        # increment to next part
        self.part_num_sent += 1

        return part


    @property
    def is_complete(self):
        return self.sent_complete



class SeedQrEncoder(BaseQrEncoder):
    def __init__(self, seed_phrase: List[str], wordlist_language_code: str):
        super().__init__()
        self.seed_phrase = seed_phrase
        self.wordlist = Seed.get_wordlist(wordlist_language_code)
        
        if self.wordlist == None:
            raise Exception('Wordlist Required')


    def seq_len(self):
        return 1


    def next_part(self):
        data = ""
        # Output as Numeric data format
        for word in self.seed_phrase:
            index = self.wordlist.index(word)
            data += str("%04d" % index)
        return data


    @property
    def is_complete(self):
        return True



class CompactSeedQrEncoder(SeedQrEncoder):
    def next_part(self):
        # Output as binary data format
        binary_str = ""
        for word in self.seed_phrase:
            index = self.wordlist.index(word)

            # Convert index to binary, strip out '0b' prefix; zero-pad to 11 bits
            binary_str += bin(index).split('b')[1].zfill(11)

        # We can exclude the checksum bits at the end
        if len(self.seed_phrase) == 24:
            # 8 checksum bits in a 24-word seed
            binary_str = binary_str[:-8]

        elif len(self.seed_phrase) == 12:
            # 4 checksum bits in a 12-word seed
            binary_str = binary_str[:-4]

        # Now convert to bytes, 8 bits at a time
        as_bytes = bytearray()
        for i in range(0, math.ceil(len(binary_str) / 8)):
            # int conversion reads byte data as a string prefixed with '0b'
            as_bytes.append(int('0b' + binary_str[i*8:(i+1)*8], 2))
        
        # Must return data as `bytes` for `qrcode` to properly recognize it as byte data
        return bytes(as_bytes)



class ChiaAddressEncoder(BaseQrEncoder):
    def __init__(self, address: str):
        super().__init__()
        self.address = address


    def seq_len(self):
        return 1


    def next_part(self):
        return self.address


    @property
    def is_complete(self):
        return True


class XpubQrEncoder(BaseQrEncoder):
    def __init__(self, seed_phrase, passphrase, derivation, network, wordlist_language_code):
        self.seed_phrase = seed_phrase
        self.passphrase = passphrase
        self.derivation = derivation
        self.network = network
        self.wordlist = Seed.get_wordlist(wordlist_language_code)
        self.parts = []
        self.part_num_sent = 0
        self.sent_complete = False

        if self.wordlist == None:
            raise Exception('Wordlist Required')
            
        version = bip32.detect_version(self.derivation, default="xpub", network=NETWORKS[SettingsConstants.map_network_to_embit(self.network)])
        self.seed = Seed(mnemonic=self.seed_phrase,
                         passphrase=self.passphrase,
                         wordlist_language_code=wordlist_language_code)
        self.root = bip32.HDKey.from_seed(self.seed.seed_bytes, version=NETWORKS[SettingsConstants.map_network_to_embit(self.network)]["xprv"])
        self.fingerprint = self.root.child(0).fingerprint
        self.xprv = self.root.derive(self.derivation)
        self.xpub = self.xprv.to_public()
        self.xpub_base58 = self.xpub.to_string(version=version)

        self.xpubstring = "[{}{}]{}".format(
            hexlify(self.fingerprint).decode('utf-8'),
            self.derivation[1:],
            self.xpub_base58
        )

        self._create_parts()


    def _create_parts(self):
        self.parts = []
        self.parts.append(self.xpubstring)


    def next_part(self) -> str:
        if len(self.parts) > 0:
            self.sent_complete = True
            return self.parts[0]


    def seq_len(self):
        return len(self.parts)


    @property
    def is_complete(self):
        return self.sent_complete



class SpecterXPubQrEncoder(XpubQrEncoder):
    def __init__(self, qr_density, **kwargs):
        # Must set up qr_max_fragment_size before calling super().__init__()
        self.qr_max_fragment_size = 65
        if qr_density == SettingsConstants.DENSITY__LOW:
            self.qr_max_fragment_size = 40
        elif qr_density == SettingsConstants.DENSITY__MEDIUM:
            self.qr_max_fragment_size = 65
        elif qr_density == SettingsConstants.DENSITY__HIGH:
            self.qr_max_fragment_size = 90

        super().__init__(**kwargs)


    def _create_parts(self):
        self.parts = []

        start = 0
        stop = self.qr_max_fragment_size
        qr_cnt = ((len(self.xpubstring)-1) // self.qr_max_fragment_size) + 1

        if qr_cnt == 1:
            self.parts.append(self.xpubstring[start:stop])

        cnt = 0
        while cnt < qr_cnt and qr_cnt != 1:
            part = "p" + str(cnt+1) + "of" + str(qr_cnt) + " " + self.xpubstring[start:stop]
            self.parts.append(part)

            start = start + self.qr_max_fragment_size
            stop = stop + self.qr_max_fragment_size
            if stop > len(self.xpubstring):
                stop = len(self.xpubstring)
            cnt += 1


    def next_part(self) -> str:
        # if part num sent is gt number of parts, start at 0
        if self.part_num_sent > (len(self.parts) - 1):
            self.part_num_sent = 0

        part = self.parts[self.part_num_sent]

        # when parts sent eq num of parts in list
        if self.part_num_sent == (len(self.parts) - 1):
            self.sent_complete = True

        # increment to next part
        self.part_num_sent += 1

        return part



class UrXpubQrEncoder(XpubQrEncoder):
    def __init__(self, qr_density, **kwargs):
        super().__init__(**kwargs)
        
        if qr_density == SettingsConstants.DENSITY__LOW:
            self.qr_max_fragment_size = 10
        elif qr_density == SettingsConstants.DENSITY__MEDIUM:
            self.qr_max_fragment_size = 30
        elif qr_density == SettingsConstants.DENSITY__HIGH:
            self.qr_max_fragment_size = 120
        
        def derivation_to_keypath(path: str) -> list:
            arr = path.split("/")
            if arr[0] == "m":
                arr = arr[1:]
            if len(arr) == 0:
                return Keypath([],self.root.my_fingerprint, None)
            if arr[-1] == "":
                # trailing slash
                arr = arr[:-1]

            for i, e in enumerate(arr):
                if e[-1] == "h" or e[-1] == "'":
                    arr[i] = PathComponent(int(e[:-1]), True)
                else:
                    arr[i] = PathComponent(int(e), False)
                    
            return Keypath(arr, self.root.my_fingerprint, len(arr))
            
        origin = derivation_to_keypath(self.derivation)
        
        self.ur_hdkey = HDKey({ 'key': self.xpub.key.serialize(),
        'chain_code': self.xpub.chain_code,
        'origin': origin,
        'parent_fingerprint': self.xpub.fingerprint})

        ur_outputs = []

        if len(origin.components) > 0:
            if origin.components[0].index == 84: # Native Single Sig
                ur_outputs.append(Output([SCRIPT_EXPRESSION_TAG_MAP[404]],self.ur_hdkey))
            elif origin.components[0].index == 49: # Nested Single Sig
                ur_outputs.append(Output([SCRIPT_EXPRESSION_TAG_MAP[400], SCRIPT_EXPRESSION_TAG_MAP[404]],self.ur_hdkey))
            elif origin.components[0].index == 48: # Multisig
                if len(origin.components) >= 4:
                    if origin.components[3].index == 2:  # Native Multisig
                        ur_outputs.append(Output([SCRIPT_EXPRESSION_TAG_MAP[401]],self.ur_hdkey))
                    elif origin.components[3].index == 1:  # Nested Multisig
                        ur_outputs.append(Output([SCRIPT_EXPRESSION_TAG_MAP[400], SCRIPT_EXPRESSION_TAG_MAP[401]],self.ur_hdkey))
            elif origin.components[0].index == 86: # P2TR
                ur_outputs.append(Output([SCRIPT_EXPRESSION_TAG_MAP[409]],self.ur_hdkey))
        
        # If empty, add all script types
        if len(ur_outputs) == 0:
            ur_outputs.append(Output([SCRIPT_EXPRESSION_TAG_MAP[404]],self.ur_hdkey))
            ur_outputs.append(Output([SCRIPT_EXPRESSION_TAG_MAP[400], SCRIPT_EXPRESSION_TAG_MAP[404]],self.ur_hdkey))
            ur_outputs.append(Output([SCRIPT_EXPRESSION_TAG_MAP[401]],self.ur_hdkey))
            ur_outputs.append(Output([SCRIPT_EXPRESSION_TAG_MAP[400], SCRIPT_EXPRESSION_TAG_MAP[401]],self.ur_hdkey))
            ur_outputs.append(Output([SCRIPT_EXPRESSION_TAG_MAP[403]],self.ur_hdkey))
        
        ur_account = Account(self.root.my_fingerprint, ur_outputs)

        qr_ur_bytes = UR("crypto-account", ur_account.to_cbor())

        self.ur2_encode = UREncoder(ur=qr_ur_bytes, max_fragment_len=self.qr_max_fragment_size)


    def seq_len(self):
        return self.ur2_encode.fountain_encoder.seq_len()


    def next_part(self) -> str:
        return self.ur2_encode.next_part().upper()
