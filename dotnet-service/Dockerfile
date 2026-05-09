FROM mcr.microsoft.com/dotnet/sdk:8.0 AS builder

WORKDIR /src
COPY obi-demo.csproj .
RUN dotnet restore

COPY Program.cs .
COPY DemoServiceImpl.cs .
COPY Protos/ Protos/
RUN dotnet publish -c Release -o /app/publish

FROM mcr.microsoft.com/dotnet/aspnet:8.0
WORKDIR /app
COPY --from=builder /app/publish .

EXPOSE 8085 9085

CMD ["dotnet", "obi-demo.dll"]