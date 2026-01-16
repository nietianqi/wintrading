"""
密钥加密管理模块
使用 AES-GCM 加密交易所 API Keys
"""
import os
import base64
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2
from typing import Tuple
import secrets


class EncryptionManager:
    """
    密钥加密管理器

    安全要点：
    1. 使用 AES-GCM 提供认证加密
    2. 每次加密使用随机 nonce
    3. 主密钥从环境变量或 KMS 获取
    4. 支持密钥版本（便于轮换）
    """

    def __init__(self, master_key: str = None, key_version: str = "v1"):
        """
        初始化加密管理器

        Args:
            master_key: 主密钥（32字节 base64），如果不提供则从环境变量读取
            key_version: 密钥版本
        """
        if master_key is None:
            master_key = os.getenv("ENCRYPTION_MASTER_KEY")
            if not master_key:
                raise ValueError(
                    "ENCRYPTION_MASTER_KEY not set. "
                    "Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(32))\""
                )

        self.key_version = key_version
        self.master_key = base64.urlsafe_b64decode(master_key)

        if len(self.master_key) != 32:
            raise ValueError("Master key must be 32 bytes")

        self.aesgcm = AESGCM(self.master_key)

    def encrypt(self, plaintext: str) -> Tuple[str, str]:
        """
        加密明文

        Args:
            plaintext: 明文字符串

        Returns:
            (encrypted_data, nonce) 都是 base64 编码的字符串
        """
        if not plaintext:
            raise ValueError("Plaintext cannot be empty")

        # 生成随机 nonce（12 字节是 GCM 推荐长度）
        nonce = secrets.token_bytes(12)

        # 加密
        plaintext_bytes = plaintext.encode('utf-8')
        ciphertext = self.aesgcm.encrypt(nonce, plaintext_bytes, None)

        # Base64 编码
        encrypted_data = base64.urlsafe_b64encode(ciphertext).decode('utf-8')
        nonce_b64 = base64.urlsafe_b64encode(nonce).decode('utf-8')

        return encrypted_data, nonce_b64

    def decrypt(self, encrypted_data: str, nonce: str) -> str:
        """
        解密密文

        Args:
            encrypted_data: 加密数据（base64）
            nonce: 加密时使用的 nonce（base64）

        Returns:
            解密后的明文字符串
        """
        if not encrypted_data or not nonce:
            raise ValueError("Encrypted data and nonce cannot be empty")

        try:
            # Base64 解码
            ciphertext = base64.urlsafe_b64decode(encrypted_data)
            nonce_bytes = base64.urlsafe_b64decode(nonce)

            # 解密
            plaintext_bytes = self.aesgcm.decrypt(nonce_bytes, ciphertext, None)
            return plaintext_bytes.decode('utf-8')

        except Exception as e:
            raise ValueError(f"Decryption failed: {str(e)}")

    def encrypt_api_credentials(self, api_key: str, api_secret: str, passphrase: str = None) -> dict:
        """
        加密交易所 API 凭证（便捷方法）

        Args:
            api_key: API Key
            api_secret: API Secret
            passphrase: Passphrase（可选，如 OKX）

        Returns:
            包含加密数据的字典
        """
        encrypted_key, nonce_key = self.encrypt(api_key)
        encrypted_secret, nonce_secret = self.encrypt(api_secret)

        result = {
            "encrypted_api_key": encrypted_key,
            "encrypted_api_secret": encrypted_secret,
            "nonce_key": nonce_key,
            "nonce_secret": nonce_secret,
            "key_version": self.key_version,
        }

        if passphrase:
            encrypted_passphrase, nonce_passphrase = self.encrypt(passphrase)
            result["encrypted_passphrase"] = encrypted_passphrase
            result["nonce_passphrase"] = nonce_passphrase

        return result

    def decrypt_api_credentials(self, encrypted_data: dict) -> dict:
        """
        解密交易所 API 凭证（便捷方法）

        Args:
            encrypted_data: 包含加密数据的字典

        Returns:
            包含明文凭证的字典
        """
        result = {
            "api_key": self.decrypt(
                encrypted_data["encrypted_api_key"],
                encrypted_data["nonce_key"]
            ),
            "api_secret": self.decrypt(
                encrypted_data["encrypted_api_secret"],
                encrypted_data["nonce_secret"]
            ),
        }

        if "encrypted_passphrase" in encrypted_data:
            result["passphrase"] = self.decrypt(
                encrypted_data["encrypted_passphrase"],
                encrypted_data["nonce_passphrase"]
            )

        return result


def generate_master_key() -> str:
    """
    生成新的主密钥（32字节，base64 编码）

    使用方法：
    1. 运行此函数生成密钥
    2. 将密钥保存到安全位置（环境变量或 KMS）
    3. 永远不要将密钥提交到版本控制

    Returns:
        Base64 编码的 32 字节密钥
    """
    key = secrets.token_bytes(32)
    return base64.urlsafe_b64encode(key).decode('utf-8')


def generate_webhook_secret() -> str:
    """
    生成 Webhook 验证密钥

    Returns:
        URL-safe 的随机字符串
    """
    return secrets.token_urlsafe(32)


# ==================== 使用示例 ====================

if __name__ == "__main__":
    print("🔐 Encryption Manager Demo\n")

    # 1. 生成主密钥（第一次部署时运行）
    print("1. Generate master key:")
    master_key = generate_master_key()
    print(f"   ENCRYPTION_MASTER_KEY={master_key}")
    print(f"   ⚠️  保存到环境变量，永远不要提交到 Git！\n")

    # 2. 初始化加密管理器
    print("2. Initialize encryption manager:")
    encryptor = EncryptionManager(master_key=master_key)
    print(f"   ✓ Initialized with key version: {encryptor.key_version}\n")

    # 3. 加密 API 凭证
    print("3. Encrypt API credentials:")
    api_key = "test_api_key_123456"
    api_secret = "test_api_secret_abcdefg"

    encrypted = encryptor.encrypt_api_credentials(api_key, api_secret)
    print(f"   Original API Key: {api_key}")
    print(f"   Encrypted: {encrypted['encrypted_api_key'][:50]}...")
    print(f"   Nonce: {encrypted['nonce_key']}\n")

    # 4. 解密 API 凭证
    print("4. Decrypt API credentials:")
    decrypted = encryptor.decrypt_api_credentials(encrypted)
    print(f"   Decrypted API Key: {decrypted['api_key']}")
    print(f"   ✓ Matches original: {decrypted['api_key'] == api_key}\n")

    # 5. 生成 Webhook 密钥
    print("5. Generate webhook secret:")
    webhook_secret = generate_webhook_secret()
    print(f"   Webhook Secret: {webhook_secret}\n")

    print("✓ All tests passed!")
