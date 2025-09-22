"""커스텀 예외 클래스들"""


class InspectionError(Exception):
    """검사 시스템의 기본 예외 클래스"""
    pass


class ConfigurationError(InspectionError):
    """설정 관련 오류"""
    pass


class FileHandlingError(InspectionError):
    """파일 처리 관련 오류"""
    pass


class BarcodeError(InspectionError):
    """바코드 관련 오류"""
    pass


class SessionError(InspectionError):
    """세션 관리 관련 오류"""
    pass


class ValidationError(InspectionError):
    """데이터 검증 관련 오류"""
    pass


class NetworkError(InspectionError):
    """네트워크 관련 오류"""
    pass


class UpdateError(InspectionError):
    """업데이트 관련 오류"""
    pass